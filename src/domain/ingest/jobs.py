"""Phase 1 sync jobs for one shop. Raw -> raw_api_responses (via DbRawSink, committed per
response) -> normalized upserts. Cursor per resource in integration_sync_state."""
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.analytics.finance_fields import SETTLED_STATUSES
from src.db.models import (
    Order,
    OrderItem,
    Payout,
    Product,
    ProductMetric,
    Settlement,
    Shop,
    Sku,
    Video,
    VideoMetric,
)
from src.db.models_finance import OrderStatementRecord, OrderStatementSkuRecord, ShopMetric
from src.domain.ingest import mappers as m
from src.domain.ingest.raw_store import DbRawSink
from src.domain.ingest.state import (
    days_to_sync,
    next_cursor,
    time_window,
)
from src.domain.ingest.upserts import (
    product_ids,
    sku_ids,
    upsert,
    upsert_map,
    video_ids,
)
from src.integrations.sync_state import SyncStateStore
from src.integrations.tiktok_shop.client import TikTokShopClient

log = logging.getLogger("tt.ingest")
INTEGRATION = m.INTEGRATION


@dataclass
class IngestContext:
    session: Session
    client: TikTokShopClient
    shop: Shop
    sink: DbRawSink
    state: SyncStateStore
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def shop_id(self) -> int:
        return self.shop.id

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.shop.timezone or "Asia/Jakarta")

    def today_local(self) -> date:
        return self.now.astimezone(self.tz).date()


def _run(ctx: IngestContext, resource: str, fn) -> dict[str, Any]:
    """fn(cursor) -> (new_cursor, counts). One transaction per resource: on error every uncommitted
    normalized write is rolled back (raw rows are committed by the sink and survive; `sync_metrics`
    commits per day, so earlier days survive too). Never raises: returns {"error": ...}."""
    key = (INTEGRATION, resource, str(ctx.shop_id))
    ctx.state.start_attempt(*key)
    try:
        cursor, counts = fn(ctx.state.get(*key).cursor)
        ctx.session.commit()
        ctx.state.mark_success(*key, cursor)
        log.info("%s ok cursor=%s %s", resource, cursor, counts)
        return counts
    except Exception as e:
        ctx.session.rollback()
        log.exception("%s failed", resource)
        try:
            ctx.state.mark_error(*key, f"{type(e).__name__}: {e}")
        except Exception:
            log.exception("%s: mark_error failed", resource)
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


# --- bootstrap ---------------------------------------------------------------------
def ensure_shop(session: Session, client: TikTokShopClient, sink: DbRawSink, *,
                currency: str, timezone: str, shop_cipher: str | None = None) -> Shop:
    shops = client.get_authorized_shops()
    if not shops:
        raise RuntimeError("no authorized shops")
    if shop_cipher:
        chosen = next((s for s in shops if s.get("cipher") == shop_cipher), None)
        if chosen is None:
            raise ValueError(f"configured shop_cipher not among authorized shops "
                             f"({[str(s.get('id')) for s in shops]})")
    else:
        chosen = shops[0]
    rows = [m.map_shop(s, currency=currency, timezone=timezone) for s in shops]
    upsert(session, Shop, rows, ["platform", "external_shop_id"],
           exclude_update=["currency", "timezone", "status"])
    session.commit()
    shop = session.scalar(select(Shop).where(Shop.platform == "tiktok_shop",
                                             Shop.external_shop_id == str(chosen["id"])))
    sink.shop_id = shop.id
    return shop


# --- catalog -----------------------------------------------------------------------
def sync_catalog(ctx: IngestContext) -> dict[str, Any]:
    def go(_cursor):
        n_p = n_s = 0
        for prod in ctx.client.get_products():
            pid_map = upsert_map(ctx.session, Product, [m.map_product(prod, ctx.shop_id)],
                                 ["shop_id", "external_product_id"], "external_product_id")
            pid = pid_map[str(prod["id"])]
            skus = [m.map_sku(s, pid) for s in prod.get("skus") or []]
            upsert(ctx.session, Sku, skus, ["product_id", "external_sku_id"])
            n_p, n_s = n_p + 1, n_s + len(skus)
        return ctx.now.isoformat(timespec="seconds"), {"products": n_p, "skus": n_s}
    return _run(ctx, "catalog", go)


# --- orders ------------------------------------------------------------------------
def sync_orders(ctx: IngestContext, since: datetime | None = None,
                until: datetime | None = None, default_days: int = 60) -> dict[str, Any]:
    """since/until given => create_time window (backfill); else update_time from cursor."""
    def go(cursor):
        if since is not None:
            ge, lt = int(since.timestamp()), int((until or ctx.now).timestamp())
            it = ctx.client.get_orders(create_time_ge=ge, create_time_lt=lt)
        else:
            ge, lt = time_window(cursor, now=ctx.now, default_days=default_days)
            it = ctx.client.get_orders(update_time_ge=ge, update_time_lt=lt)
        n, seen = 0, []
        skus = sku_ids(ctx.session, ctx.shop_id)
        prods = product_ids(ctx.session, ctx.shop_id)
        for o in it:
            row = m.map_order(o, ctx.shop_id, ctx.shop.currency)
            oid = upsert_map(ctx.session, Order, [row], ["shop_id", "external_order_id"],
                             "external_order_id")[row["external_order_id"]]
            items = m.map_order_items(o, oid)
            for it_ in items:
                sp = skus.get(it_.pop("_external_sku_id"))
                pid = prods.get(it_.pop("_external_product_id"))
                it_["sku_id"] = sp[0] if sp else None
                it_["product_id"] = pid or (sp[1] if sp else None)
            _upsert_order_items(ctx.session, oid, items)
            seen.append(row["raw_source_updated_at"] or row["order_created_at"])
            n += 1
        return next_cursor(cursor, seen), {"orders": n, "window": [ge, lt]}
    return _run(ctx, "orders", go)


def _upsert_order_items(session: Session, order_id: int, items: list[dict]) -> None:
    """Upsert on (order_id, external_item_id) — keeps order_items.id stable for finance FKs;
    rows absent from the new payload are deleted (logged)."""
    upsert(session, OrderItem, items, ["order_id", "external_item_id"])
    keep = [i["external_item_id"] for i in items]
    gone = session.execute(delete(OrderItem).where(
        OrderItem.order_id == order_id, OrderItem.external_item_id.notin_(keep))).rowcount
    if gone:
        log.warning("order %s: %d order_items no longer in payload, deleted", order_id, gone)


# --- finance -----------------------------------------------------------------------
def sync_order_statements(ctx: IngestContext, external_order_ids: list[str] | None = None,
                          unsettled_days: int = 90) -> dict[str, Any]:
    """Per-order flat statement record. Default: orders in last `unsettled_days` that still need a
    (re)poll — see `_orders_needing_statement`. Unsettled records arrive with statement_id "" and are
    stored as-is (provisional); once a real statement lands for the order, the "" row is deleted.
    Cursor is just the run time (the order selection is DB-driven, not cursor-driven)."""
    def go(_cursor):
        ids = external_order_ids if external_order_ids is not None else \
            _orders_needing_statement(ctx, unsettled_days)
        n_rec = n_sku = n_empty = 0
        for ext in ids:
            data = ctx.client.get_order_statement_transactions(ext)
            recs = data.get("statement_transactions") or []
            if not recs:
                n_empty += 1
                continue
            rows = [m.map_order_statement_record(
                r, shop_id=ctx.shop_id, external_order_id=ext,
                order_create_time=data.get("order_create_time"),
                raw_response_id=ctx.sink.last_id, fetched_at=ctx.now) for r in recs]
            ids_by_stmt = upsert_map(ctx.session, OrderStatementRecord, rows,
                                     ["shop_id", "external_order_id", "statement_id"],
                                     "statement_id")
            for r in recs:
                rid = ids_by_stmt[str(r.get("statement_id") or "")]
                skus = m.map_order_statement_sku_records(r, rid)
                upsert(ctx.session, OrderStatementSkuRecord, skus, ["record_id", "external_sku_id"])
                n_sku += len(skus)
            n_rec += len(rows)
            if any(k for k in ids_by_stmt):
                _drop_placeholder_record(ctx, ext)
        return ctx.now.isoformat(timespec="seconds"), {"orders_polled": len(ids),
                                                       "records": n_rec, "sku_records": n_sku,
                                                       "no_statement_yet": n_empty}
    return _run(ctx, "order_statements", go)


def _drop_placeholder_record(ctx: IngestContext, external_order_id: str) -> None:
    ph = ctx.session.scalar(select(OrderStatementRecord.id).where(
        OrderStatementRecord.shop_id == ctx.shop_id,
        OrderStatementRecord.external_order_id == external_order_id,
        OrderStatementRecord.statement_id == ""))
    if ph is not None:
        ctx.session.execute(delete(OrderStatementSkuRecord)
                            .where(OrderStatementSkuRecord.record_id == ph))
        ctx.session.execute(delete(OrderStatementRecord).where(OrderStatementRecord.id == ph))


RESTATEMENT_WINDOW = timedelta(days=30)


def needs_statement_poll(*, order_status: str | None, order_updated_at: datetime | None,
                         has_settled: bool, max_fetched_at: datetime | None,
                         latest_statement_time: datetime | None, now: datetime) -> bool:
    """Only UNPAID is skipped (cancelled orders can still carry fees). Poll when there is no SETTLED
    record yet, when the order changed after we last fetched its statement (e.g. refund after
    settlement), or when its latest statement is within RESTATEMENT_WINDOW (late adjustments)."""
    if (order_status or "").upper() == "UNPAID":
        return False
    if not has_settled:
        return True
    if order_updated_at is not None and max_fetched_at is not None \
            and order_updated_at > max_fetched_at:
        return True
    return latest_statement_time is not None and latest_statement_time >= now - RESTATEMENT_WINDOW


def _orders_needing_statement(ctx: IngestContext, days: int) -> list[str]:
    since = ctx.now - timedelta(days=days)
    R = OrderStatementRecord
    agg = select(
        R.external_order_id,
        func.bool_or(R.status.in_(list(SETTLED_STATUSES))).label("settled"),
        func.max(R.fetched_at).label("fetched"),
        func.max(R.statement_time).label("stmt"),
    ).where(R.shop_id == ctx.shop_id).group_by(R.external_order_id).subquery()
    q = (select(Order.external_order_id, Order.order_status, Order.raw_source_updated_at,
                agg.c.settled, agg.c.fetched, agg.c.stmt)
         .outerjoin(agg, agg.c.external_order_id == Order.external_order_id)
         .where(Order.shop_id == ctx.shop_id, Order.order_created_at >= since)
         .order_by(Order.order_created_at))
    return [ext for ext, st, upd, settled, fetched, stmt in ctx.session.execute(q)
            if needs_statement_poll(order_status=st, order_updated_at=upd,
                                    has_settled=bool(settled), max_fetched_at=fetched,
                                    latest_statement_time=stmt, now=ctx.now)]


def sync_statements(ctx: IngestContext, since: datetime | None = None,
                    until: datetime | None = None, default_days: int = 60) -> dict[str, Any]:
    def go(cursor):
        if since is not None:
            ge, lt = int(since.timestamp()), int((until or ctx.now).timestamp())
        else:
            ge, lt = time_window(cursor, now=ctx.now, default_days=default_days,
                                 overlap=timedelta(days=7))  # payment_status flips later
        n, seen = 0, []
        for s in ctx.client.get_finance_statements(statement_time_ge=ge, statement_time_lt=lt):
            row = m.map_statement(s, ctx.shop_id, ctx.shop.currency)
            upsert(ctx.session, Settlement, [row], ["shop_id", "external_settlement_id"])
            seen.append(row["settlement_at"])
            n += 1
        return next_cursor(cursor, seen), {"statements": n, "window": [ge, lt]}
    return _run(ctx, "statements", go)


def sync_withdrawals(ctx: IngestContext) -> dict[str, Any]:
    def go(_cursor):
        rows = [m.map_withdrawal(w, ctx.shop_id, ctx.shop.currency)
                for w in ctx.client.get_withdrawals()]
        upsert(ctx.session, Payout, rows, ["shop_id", "external_payout_id"])
        return ctx.now.isoformat(timespec="seconds"), {"withdrawals": len(rows)}
    return _run(ctx, "withdrawals", go)


# --- analytics (daily) -------------------------------------------------------------
def _day_range(day: date) -> tuple[str, str]:
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


def sync_video_metrics(ctx: IngestContext, day: date) -> dict[str, Any]:
    start, end = _day_range(day)
    vids = video_ids(ctx.session, ctx.shop_id)
    n = 0
    for v in ctx.client.get_video_performance(start, end):
        ext = str(v["id"])
        if ext not in vids:
            vids.update(upsert_map(ctx.session, Video, [m.map_video(v, ctx.shop_id)],
                                   ["shop_id", "external_video_id"], "external_video_id"))
        upsert(ctx.session, VideoMetric, [m.map_video_metric(v, vids[ext], day, ctx.now)],
               ["video_id", "metric_date", "metric_hour"])
        n += 1
    return {"video_metrics": n}


def sync_product_metrics(ctx: IngestContext, day: date) -> dict[str, Any]:
    start, end = _day_range(day)
    prods, n, skipped = product_ids(ctx.session, ctx.shop_id), 0, 0
    for p in ctx.client.get_product_performance(start, end):
        pid = prods.get(str(p["id"]))
        if pid is None:
            skipped += 1
            continue
        upsert(ctx.session, ProductMetric, [m.map_product_metric(p, pid, day, ctx.now)],
               ["product_id", "sku_id", "metric_date"])
        n += 1
    return {"product_metrics": n, "unknown_products": skipped}


def sync_sku_metrics(ctx: IngestContext, day: date) -> dict[str, Any]:
    start, end = _day_range(day)
    skus, n, skipped = sku_ids(ctx.session, ctx.shop_id), 0, 0
    for s in ctx.client.get_sku_performance(start, end):
        sp = skus.get(str(s["id"]))
        if sp is None:
            skipped += 1
            continue
        upsert(ctx.session, ProductMetric, [m.map_sku_metric(s, sp[1], sp[0], day, ctx.now)],
               ["product_id", "sku_id", "metric_date"])
        n += 1
    return {"sku_metrics": n, "unknown_skus": skipped}


def sync_shop_metrics(ctx: IngestContext, day: date) -> dict[str, Any]:
    start, end = _day_range(day)
    data = ctx.client.get_shop_performance(start, end)
    upsert(ctx.session, ShopMetric, [m.map_shop_metric(data, ctx.shop_id, day, ctx.now)],
           ["shop_id", "metric_date"])
    return {"shop_metrics": 1}


_METRIC_JOBS = {"video_metrics": sync_video_metrics, "product_metrics": sync_product_metrics,
                "sku_metrics": sync_sku_metrics, "shop_metrics": sync_shop_metrics}


def sync_metrics(ctx: IngestContext, days: int = 60, resources: tuple[str, ...] = tuple(_METRIC_JOBS)
                 ) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for res in resources:
        fn = _METRIC_JOBS[res]

        def go(cursor, fn=fn):
            total: dict[str, int] = {}
            days_ = days_to_sync(cursor, today_local=ctx.today_local(), default_days=days)
            for d in days_:
                for k, v in fn(ctx, d).items():
                    total[k] = total.get(k, 0) + v
                ctx.session.commit()
            new_cursor = days_[-1].isoformat() if days_ else cursor
            return new_cursor, {**total, "days": len(days_)}
        out[res] = _run(ctx, res, go)
    return out


# --- backfill ----------------------------------------------------------------------
def backfill(ctx: IngestContext, days: int = 60) -> dict[str, Any]:
    since = ctx.now - timedelta(days=days)
    out = {"catalog": sync_catalog(ctx), "orders": sync_orders(ctx, since=since)}
    out["order_statements"] = sync_order_statements(ctx, unsettled_days=days)
    out["statements"] = sync_statements(ctx, since=since)
    out["withdrawals"] = sync_withdrawals(ctx)
    out["metrics"] = sync_metrics(ctx, days=days)
    return out
