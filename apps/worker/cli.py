"""python -m apps.worker.cli <command> — Phase 1 ingestion for one shop (no scheduler)."""
import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from src.config.settings import settings
from src.db.models import (
    IntegrationSyncState,
    Order,
    OrderItem,
    Payout,
    Product,
    ProductMetric,
    RawApiResponse,
    Settlement,
    Shop,
    Sku,
    SkuCostVersion,
    Video,
    VideoMetric,
)
from src.db.models_finance import OrderStatementRecord, ShopMetric
from src.db.session import SessionLocal
from src.domain.ingest import jobs
from src.domain.ingest.cogs import load_cogs, parse_cogs_csv
from src.domain.ingest.raw_store import DbRawSink
from src.domain.ingest.state import DbSyncStateStore
from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient

log = logging.getLogger("tt.cli")


def build_context(session) -> jobs.IngestContext:
    store = TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json")
    tokens = FileTokenProvider(store, settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
    sink = DbRawSink(session, None)
    client = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, tokens,
                              shop_cipher=settings.tiktok_shop_shop_cipher or None, raw_sink=sink)
    shop = jobs.ensure_shop(session, client, sink, currency=settings.shop_currency,
                            timezone=settings.shop_timezone,
                            shop_cipher=settings.tiktok_shop_shop_cipher or None)
    return jobs.IngestContext(session=session, client=client, shop=shop, sink=sink,
                              state=DbSyncStateStore(session))


def shop_from_db(session) -> Shop:
    """DB-only shop lookup (no API call): configured cipher, else the single tiktok_shop row."""
    q = select(Shop).where(Shop.platform == "tiktok_shop")
    if settings.tiktok_shop_shop_cipher:
        q = q.where(Shop.shop_cipher == settings.tiktok_shop_shop_cipher)
    shop = session.scalar(q.order_by(Shop.id))
    if shop is None:
        raise RuntimeError("shop not in DB yet; run `catalog` (or any sync) first")
    return shop


def cmd_status(session) -> dict:
    counts = {t.__tablename__: session.scalar(select(func.count()).select_from(t)) for t in (
        Shop, Product, Sku, SkuCostVersion, Order, OrderItem, OrderStatementRecord, Settlement,
        Payout, Video, VideoMetric, ProductMetric, ShopMetric, RawApiResponse)}
    states = [{"resource": s.resource_type, "cursor": s.cursor, "status": s.status,
               "last_success": s.last_successful_sync.isoformat() if s.last_successful_sync else None,
               "error": (s.error or "")[:200] or None}
              for s in session.scalars(select(IntegrationSyncState)
                                       .order_by(IntegrationSyncState.resource_type))]
    return {"counts": counts, "sync_state": states}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="apps.worker.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalog")
    for name in ("orders", "statements"):
        sp = sub.add_parser(name)
        sp.add_argument("--days", type=int, default=None,
                        help="backfill window by create/statement time; omit = incremental via cursor")
    for name in ("metrics", "backfill"):
        sp = sub.add_parser(name)
        sp.add_argument("--days", type=int, default=60)
    sp = sub.add_parser("order-statements")
    sp.add_argument("--days", type=int, default=90)
    sp.add_argument("--order-ids", default="")
    sub.add_parser("withdrawals")
    sp = sub.add_parser("cogs")
    sp.add_argument("--file", default="seed/cogs_seed.csv")
    sub.add_parser("status")
    a = p.parse_args(argv)
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)s %(message)s")
    try:
        out = run_command(a)
    except Exception as e:
        log.exception("%s failed", a.cmd)
        print(json.dumps({"error": f"{type(e).__name__}: {str(e)[:500]}"}, indent=2))
        return 1
    print(json.dumps(out, indent=2, default=str))
    return 0


def run_command(a: argparse.Namespace) -> dict:
    with SessionLocal() as session:
        if a.cmd == "status":
            return cmd_status(session)
        if a.cmd == "cogs":
            shop = shop_from_db(session)
            return {"shop": shop.external_shop_id,
                    "result": load_cogs(session, shop.id, parse_cogs_csv(a.file),
                                        settings.shop_currency)}
        ctx = build_context(session)
        days = getattr(a, "days", None)
        since = ctx.now - timedelta(days=days) if days else None
        if a.cmd == "catalog":
            out = jobs.sync_catalog(ctx)
        elif a.cmd == "orders":
            out = jobs.sync_orders(ctx, since=since)
        elif a.cmd == "order-statements":
            ids = [x for x in a.order_ids.split(",") if x] or None
            out = jobs.sync_order_statements(ctx, ids, unsettled_days=a.days)
        elif a.cmd == "statements":
            out = jobs.sync_statements(ctx, since=since)
        elif a.cmd == "withdrawals":
            out = jobs.sync_withdrawals(ctx)
        elif a.cmd == "metrics":
            out = jobs.sync_metrics(ctx, days=a.days)
        elif a.cmd == "backfill":
            out = jobs.backfill(ctx, days=a.days)
        else:
            raise ValueError(f"unknown command {a.cmd}")
        return {"shop": ctx.shop.external_shop_id, "raw_responses_stored": ctx.sink.count,
                "at": datetime.now(UTC).isoformat(timespec="seconds"), "result": out}


if __name__ == "__main__":
    sys.exit(main())
