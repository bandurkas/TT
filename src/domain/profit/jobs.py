"""Compute and persist per-order profit for one shop.

Sources: order_statement_records(+sku) -> FinanceTxn (finance_fields adapter), sku_cost_versions ->
COGS, settlements classified AD_DEDUCTION -> ad cost (BLENDED, trailing 7-day window, LOW confidence).
Orders without a settled record get a clearly labelled PROVISIONAL estimate (estimate_provisional).
Decimal only. Versioned rows: a new version is inserted only when the inputs hash changes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.analytics.attribution import AttributionMethod, Confidence, blended
from src.analytics.finance_fields import SETTLED_STATUSES, StatementKind, classify_statement
from src.analytics.finance_fields import statement_record_to_txns as _record_to_txns
from src.analytics.profitability import (
    AllocatedAds,
    CostVersion,
    FinanceTxn,
    OrderItemInput,
    order_profit,
    pick_cost_version,
    revenue_breakdown,
)
from src.analytics.profitability import OrderProfit as EngineProfit
from src.analytics.transaction_types import quantum
from src.db.models import Order, OrderItem, Product, Settlement, Shop, Sku, SkuCostVersion
from src.db.models import OrderProfit as OrderProfitRow
from src.db.models_finance import (
    STATEMENT_AMOUNT_FIELDS,
    OrderStatementRecord,
    OrderStatementSkuRecord,
)

log = logging.getLogger("tt.profit")

ZERO = Decimal(0)
RATIO_PLACES = Decimal("0.000001")
AD_WINDOW_DAYS = 7
FEE_RATIO_DAYS = 30
DEFAULT_TZ = "Asia/Jakarta"
SKIP_ORDER_STATUSES = frozenset({"CANCELLED", "CANCEL", "UNPAID"})  # UNVERIFIED names
PROVISIONAL_LABEL = "PROVISIONAL ESTIMATE: no settled statement; fees estimated from trailing 30-day ratio"
NO_COGS_VERSION_FROM = date(1970, 1, 1)


# --- inputs ------------------------------------------------------------------------------
@dataclass
class OrderCtx:
    order: Any  # Order-like: id, external_order_id, order_created_at, order_status, currency, ...
    items: list[Any] = field(default_factory=list)  # OrderItem-like
    record: Any | None = None  # OrderStatementRecord-like (settled)
    sku_records: list[Any] = field(default_factory=list)  # OrderStatementSkuRecord-like
    sku_external_by_id: dict[int, str] = field(default_factory=dict)
    product_by_sku_ext: dict[str, int | None] = field(default_factory=dict)


@dataclass
class ProfitInputs:
    shop_id: int
    currency: str
    timezone: str
    orders: list[OrderCtx]
    cost_versions: list[CostVersion]  # sku_id = external sku id
    settlements: list[Any]  # Settlement-like rows
    fee_ratio_records: list[Any] = field(default_factory=list)  # settled records for fee ratio


@dataclass
class OrderProfitCalc:
    order_id: int
    external_order_id: str
    local_date: date
    profit: EngineProfit
    snapshot: dict[str, Any]
    is_estimate: bool
    items: list[dict[str, Any]]  # per-item split for product aggregates

    @property
    def hash(self) -> str:
        return self.snapshot["hash"]


# --- helpers -----------------------------------------------------------------------------
def local_date(ts: datetime | None, tz: str) -> date | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(ZoneInfo(tz)).date()


def _dec(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v)) if v is not None else ZERO


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def record_to_dict(record: Any, sku_records: Iterable[Any] = ()) -> dict[str, Any]:
    """ORM statement record -> flat dict shaped like the Finance API payload."""
    st = getattr(record, "statement_time", None)
    out: dict[str, Any] = {
        "id": _s(getattr(record, "external_transaction_id", None)) or _s(getattr(record, "id", None)),
        "statement_id": _s(getattr(record, "statement_id", None)),
        "statement_time": int(st.timestamp()) if isinstance(st, datetime) else st,
        "status": getattr(record, "status", None),
        "currency": getattr(record, "currency", None),
    }
    for f in STATEMENT_AMOUNT_FIELDS:
        v = getattr(record, f, None)
        if v is not None:
            out[f] = str(v)
    skus = []
    for s in sku_records:
        d: dict[str, Any] = {"sku_id": _s(getattr(s, "external_sku_id", None)),
                             "sku_name": getattr(s, "sku_name", None),
                             "product_name": getattr(s, "product_name", None),
                             "quantity": getattr(s, "quantity", None),
                             "currency": getattr(s, "currency", None) or out["currency"]}
        for f in STATEMENT_AMOUNT_FIELDS:
            v = getattr(s, f, None)
            if v is not None:
                d[f] = str(v)
        skus.append(d)
    if skus:
        out["sku_statement_transactions"] = skus
    return out


def build_txns(ctx: OrderCtx) -> list[FinanceTxn]:
    if ctx.record is None:
        return []
    rec = record_to_dict(ctx.record, ctx.sku_records)
    sku_to_item = {}
    for it in ctx.items:
        ext = ctx.sku_external_by_id.get(getattr(it, "sku_id", None))
        if ext and ext not in sku_to_item:
            sku_to_item[ext] = str(it.id)
    return _record_to_txns(rec, ctx.order.external_order_id, sku_to_item=sku_to_item)


def build_items(ctx: OrderCtx, currency: str) -> list[OrderItemInput]:
    """OrderItemInput from order_items; fallback to statement SKU records when items are missing."""
    out: list[OrderItemInput] = []
    for it in ctx.items:
        ext = ctx.sku_external_by_id.get(getattr(it, "sku_id", None)) or f"unknown-sku:{it.id}"
        qty = int(getattr(it, "quantity", 0) or 0) or 1
        price = getattr(it, "unit_sale_price", None)
        if price is None:
            g = getattr(it, "gross_item_value", None)
            price = (_dec(g) / qty) if g is not None else ZERO
        out.append(OrderItemInput(order_item_id=str(it.id), sku_id=ext, quantity=qty,
                                  unit_sale_price=_dec(price), currency=currency))
    if out:
        return out
    for s in ctx.sku_records:
        qty = int(getattr(s, "quantity", 0) or 0) or 1
        gross = _dec(getattr(s, "gross_sales_amount", None))
        ext = str(s.external_sku_id)
        out.append(OrderItemInput(order_item_id=ext, sku_id=ext, quantity=qty,
                                  unit_sale_price=gross / qty, currency=currency))
    return out


def cost_versions_with_fallback(versions: Sequence[CostVersion], items: Sequence[OrderItemInput],
                                on: date, currency: str) -> tuple[list[CostVersion], list[str]]:
    """Missing COGS -> zero-cost version + warning (never raise, never hide)."""
    out = list(versions)
    warnings: list[str] = []
    for it in items:
        try:
            pick_cost_version(versions, it.sku_id, on)
        except LookupError:
            warnings.append(f"COGS missing for sku {it.sku_id} on {on}; cogs=0")
            out.append(CostVersion(sku_id=it.sku_id, effective_from=NO_COGS_VERSION_FROM,
                                   effective_to=None, cogs_per_unit=ZERO, currency=currency))
    return out, warnings


# --- ad deductions (BLENDED over trailing window) ---------------------------------------------
def is_ad_deduction(settlement: Any) -> bool:
    extra = getattr(settlement, "extra", None) or {}
    cls = extra.get("classification") if isinstance(extra, Mapping) else None
    if cls:
        return cls == StatementKind.AD_DEDUCTION
    gross = getattr(settlement, "gross_amount", None)
    net = getattr(settlement, "net_amount", None)
    if gross is not None and net is not None and _dec(gross) == ZERO and _dec(net) < ZERO:
        if isinstance(extra, Mapping) and extra:
            return classify_statement(extra) is StatementKind.AD_DEDUCTION
        return True
    return False


def ad_deductions_by_day(settlements: Iterable[Any], tz: str) -> dict[date, Decimal]:
    """Positive ad spend per shop-local settlement day."""
    out: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for s in settlements:
        if not is_ad_deduction(s):
            continue
        d = local_date(getattr(s, "settlement_at", None), tz)
        if d is None:
            log.warning("ad deduction %s has no settlement_at; skipped",
                        getattr(s, "external_settlement_id", "?"))
            continue
        out[d] += abs(_dec(getattr(s, "net_amount", None)))
    return dict(out)


def allocate_ads_blended(spend_by_day: Mapping[date, Decimal],
                         net_rev_by_order: Mapping[str, tuple[date, Decimal]], currency: str,
                         window_days: int = AD_WINDOW_DAYS) -> tuple[dict[str, Decimal], Decimal, list[str]]:
    """Each deduction day's spend is spread (attribution.blended) over orders whose local date lies in
    the trailing window [day-window+1, day], weighted by positive net seller revenue.
    Returns (allocation per order, unallocated spend, warnings). Sum(alloc)+unallocated == Sum(spend)."""
    alloc: dict[str, Decimal] = {k: ZERO for k in net_rev_by_order}
    unallocated = ZERO
    warnings: list[str] = []
    for day in sorted(spend_by_day):
        spend = spend_by_day[day]
        if spend == ZERO:
            continue
        lo = day - timedelta(days=window_days - 1)
        window = {k: rev for k, (d, rev) in net_rev_by_order.items() if lo <= d <= day}
        if not window:
            unallocated += spend
            warnings.append(f"ad spend {spend} on {day}: no orders in window; unallocated")
            continue
        res = blended(spend, window, currency)
        for k, v in res.allocations.items():
            alloc[k] += v
        if res.unallocated:
            unallocated += res.unallocated
            warnings.append(f"ad spend {spend} on {day}: {res.note}")
    return alloc, unallocated, warnings


# --- provisional estimate ---------------------------------------------------------------------
def trailing_fee_ratio(records: Iterable[Any], as_of: date | None, tz: str,
                       days: int = FEE_RATIO_DAYS) -> Decimal | None:
    """|fees| / revenue over settled statement records in the trailing window. None if no data."""
    fees = rev = ZERO
    for r in records:
        if str(getattr(r, "status", "") or "").upper() not in SETTLED_STATUSES:
            continue
        d = local_date(getattr(r, "statement_time", None), tz)
        if as_of is not None and d is not None and not (as_of - timedelta(days=days) <= d <= as_of):
            continue
        rev += _dec(getattr(r, "revenue_amount", None))
        fees += abs(_dec(getattr(r, "fee_amount", None)))
    return (fees / rev).quantize(RATIO_PLACES) if rev > ZERO else None


def estimate_provisional(order: Any, items: Sequence[OrderItemInput], fee_ratio: Decimal | None,
                         currency: str) -> tuple[list[FinanceTxn], list[str]]:
    """PROVISIONAL ESTIMATE (not a settlement): sale = GMV (or Σ items) - seller discount;
    fees = sale × trailing fee ratio. Txns carry no settlement_id -> engine status PROVISIONAL."""
    gmv = getattr(order, "gross_merchandise_value", None)
    sale = _dec(gmv) if gmv is not None else sum((it.gross_item_value for it in items), ZERO)
    disc = abs(_dec(getattr(order, "seller_discount", None)))
    oid = str(order.external_order_id)
    txns = [FinanceTxn(f"est:{oid}:sale", "sale", sale, currency)]
    if disc:
        txns.append(FinanceTxn(f"est:{oid}:seller_discount", "seller_discount", disc, currency))
    warnings = [PROVISIONAL_LABEL]
    if fee_ratio is None:
        warnings.append("no trailing fee data; estimated fees = 0")
        return txns, warnings
    fee = ((sale - disc) * fee_ratio).quantize(quantum(currency))
    if fee:
        txns.append(FinanceTxn(f"est:{oid}:estimated_fees", "platform_commission", fee, currency))
    warnings.append(f"estimated fees {fee} = ({sale}-{disc}) x ratio {fee_ratio}")
    return txns, warnings


# --- compute ----------------------------------------------------------------------------------
def snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    body = json.dumps({k: v for k, v in snapshot.items() if k != "hash"}, sort_keys=True,
                      default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _order_local_date(ctx: OrderCtx, tz: str) -> date:
    d = local_date(getattr(ctx.order, "order_created_at", None), tz)
    if d is None and ctx.record is not None:
        d = local_date(getattr(ctx.record, "order_create_time", None), tz)
    return d or local_date(datetime.now(UTC), tz)  # type: ignore[return-value]


def compute_from_inputs(inp: ProfitInputs, now: datetime | None = None) -> list[OrderProfitCalc]:
    now = now or datetime.now(UTC)
    tz = inp.timezone or DEFAULT_TZ
    cur = inp.currency
    as_of = max((d for d in (local_date(getattr(r, "statement_time", None), tz)
                             for r in inp.fee_ratio_records) if d), default=None)
    fee_ratio = trailing_fee_ratio(inp.fee_ratio_records, as_of, tz)

    prepared: list[tuple[OrderCtx, date, list[OrderItemInput], list[FinanceTxn], list[CostVersion],
                         list[str], bool]] = []
    for ctx in inp.orders:
        status = str(getattr(ctx.order, "order_status", "") or "").upper()
        if ctx.record is None and status in SKIP_ORDER_STATUSES:
            continue
        d = _order_local_date(ctx, tz)
        items = build_items(ctx, cur)
        if not items:
            log.warning("order %s has no items/sku records; skipped", ctx.order.external_order_id)
            continue
        if ctx.record is not None:
            txns, warns, est = build_txns(ctx), [], False
        else:
            txns, warns = estimate_provisional(ctx.order, items, fee_ratio, cur)
            est = True
        versions, cw = cost_versions_with_fallback(inp.cost_versions, items, d, cur)
        prepared.append((ctx, d, items, txns, versions, warns + cw, est))

    net_by_order = {str(ctx.order.id): (d, revenue_breakdown(txns, cur).net_seller_revenue)
                    for ctx, d, _, txns, _, _, _ in prepared}
    spend_by_day = ad_deductions_by_day(inp.settlements, tz)
    ads, unallocated, ad_warns = allocate_ads_blended(spend_by_day, net_by_order, cur)
    for w in ad_warns:
        log.warning("%s", w)
    if unallocated:
        log.warning("shop %s: unallocated ad spend %s", inp.shop_id, unallocated)

    out: list[OrderProfitCalc] = []
    for ctx, d, items, txns, versions, warns, est in prepared:
        key = str(ctx.order.id)
        allocated = AllocatedAds(ads.get(key, ZERO), cur, AttributionMethod.BLENDED, Confidence.LOW)
        p = order_profit(key, d, items, txns, versions, allocated)
        p = EngineProfit(**{**p.__dict__, "warnings": tuple(warns) + p.warnings})
        item_rows = [{
            "order_item_id": ip.order_item_id, "sku_id": ip.sku_id,
            "product_id": ctx.product_by_sku_ext.get(ip.sku_id), "quantity": ip.quantity,
            "gross_item_value": str(ip.gross_item_value),
            "net_seller_revenue": str(ip.net_seller_revenue), "cogs": str(ip.costs.total),
            "allocated_ad_cost": str(ip.allocated_ad_cost),
            "estimated_net_profit": str(ip.estimated_net_profit),
        } for ip in p.items]
        snap: dict[str, Any] = {
            "estimate": est, "fee_ratio": str(fee_ratio) if est else None,
            "txns": [(t.external_transaction_id, t.ntype.value, str(t.amount), t.settlement_id)
                     for t in txns],
            "items": item_rows,
            "cost_versions": sorted({(ip.cost_version.sku_id, str(ip.cost_version.effective_from),
                                      str(ip.cost_version.cogs_per_unit)) for ip in p.items}),
            "cogs_missing": any(w.startswith("COGS missing") for w in warns),
            "ad_cost": str(p.allocated_ad_cost), "ad_method": "BLENDED", "ad_window_days": AD_WINDOW_DAYS,
            "status": p.profit_status.value, "local_date": str(d), "warnings": list(p.warnings),
        }
        snap["hash"] = snapshot_hash(snap)
        out.append(OrderProfitCalc(ctx.order.id, ctx.order.external_order_id, d, p, snap, est, item_rows))
    return out


# --- persist (versioned) ----------------------------------------------------------------------
def row_from_calc(c: OrderProfitCalc, version: int, now: datetime) -> OrderProfitRow:
    p, r = c.profit, c.profit.revenue
    return OrderProfitRow(
        order_id=c.order_id, version=version, is_current=True, profit_status=p.profit_status.value,
        sale_proceeds=r.sale_proceeds, seller_discounts=r.seller_discounts, platform_fees=r.platform_fees,
        affiliate_commission=r.affiliate_commission, seller_shipping=r.shipping, taxes=r.taxes,
        refunds=r.refunds, subsidies=r.platform_subsidies, adjustments=r.adjustments,
        net_seller_revenue=p.net_seller_revenue, cogs=p.costs.cogs, packaging=p.costs.packaging,
        inbound_logistics=p.costs.inbound_logistics, other_variable=p.costs.other_variable,
        contribution_profit=p.contribution_profit_before_ads, allocated_ad_cost=p.allocated_ad_cost,
        attribution_method=AttributionMethod.BLENDED.value,
        attribution_confidence=Confidence.LOW.value,
        estimated_net_profit=p.estimated_net_profit, currency=p.currency, calculated_at=now,
        inputs_snapshot=c.snapshot,
    )


def persist_order_profits(session: Any, calcs: Sequence[OrderProfitCalc],
                          current: Mapping[int, Any], now: datetime | None = None) -> dict[str, int]:
    """current: order_id -> current OrderProfit row (or None). Inserts version prev+1 only when the
    inputs hash changed; otherwise no-op. Returns counts."""
    now = now or datetime.now(UTC)
    stats = {"inserted": 0, "unchanged": 0}
    for c in calcs:
        prev = current.get(c.order_id)
        prev_hash = ((getattr(prev, "inputs_snapshot", None) or {}).get("hash")) if prev else None
        if prev is not None and prev_hash == c.hash:
            stats["unchanged"] += 1
            continue
        version = 1
        if prev is not None:
            prev.is_current = False
            version = int(prev.version or 0) + 1
        session.add(row_from_calc(c, version, now))
        stats["inserted"] += 1
    return stats


# --- DB loading ---------------------------------------------------------------------------------
def load_inputs(session: Any, shop_id: int, since: date | None = None) -> ProfitInputs:
    shop = session.get(Shop, shop_id)
    if shop is None:
        raise LookupError(f"shop {shop_id} not found")
    tz = shop.timezone or DEFAULT_TZ
    q = select(Order).where(Order.shop_id == shop_id)
    if since is not None:
        # look back one ad window so blended allocation sees the full trailing revenue
        start = datetime.combine(since - timedelta(days=AD_WINDOW_DAYS), datetime.min.time(),
                                 tzinfo=ZoneInfo(tz))
        q = q.where(Order.order_created_at >= start)
    orders = list(session.scalars(q.order_by(Order.order_created_at)))
    ids = [o.id for o in orders]
    items: dict[int, list[Any]] = defaultdict(list)
    if ids:
        for it in session.scalars(select(OrderItem).where(OrderItem.order_id.in_(ids))):
            items[it.order_id].append(it)
    sku_rows = list(session.execute(
        select(Sku.id, Sku.external_sku_id, Sku.product_id).join(Product, Product.id == Sku.product_id)
        .where(Product.shop_id == shop_id)))
    sku_ext = {sid: ext for sid, ext, _ in sku_rows}
    product_by_ext = {ext: pid for _, ext, pid in sku_rows}

    records = list(session.scalars(select(OrderStatementRecord)
                                   .where(OrderStatementRecord.shop_id == shop_id)))
    settled = [r for r in records if str(r.status or "").upper() in SETTLED_STATUSES]
    rec_by_order: dict[str, Any] = {}
    for r in sorted(settled, key=lambda r: (r.statement_time or datetime.min.replace(tzinfo=UTC))):
        rec_by_order[r.external_order_id] = r  # latest statement wins
    sku_recs: dict[int, list[Any]] = defaultdict(list)
    rec_ids = [r.id for r in rec_by_order.values()]
    if rec_ids:
        for s in session.scalars(select(OrderStatementSkuRecord)
                                 .where(OrderStatementSkuRecord.record_id.in_(rec_ids))):
            sku_recs[s.record_id].append(s)

    ctxs = []
    for o in orders:
        r = rec_by_order.get(o.external_order_id)
        ctxs.append(OrderCtx(order=o, items=items.get(o.id, []), record=r,
                             sku_records=sku_recs.get(r.id, []) if r else [],
                             sku_external_by_id=sku_ext, product_by_sku_ext=product_by_ext))

    versions = []
    for v in session.scalars(select(SkuCostVersion)):
        ext = sku_ext.get(v.sku_id)
        if ext is None:
            continue
        versions.append(CostVersion(sku_id=ext, effective_from=v.effective_from, effective_to=v.effective_to,
                                    cogs_per_unit=_dec(v.cogs_per_unit), currency=v.currency,
                                    packaging_per_unit=_dec(v.packaging_per_unit),
                                    inbound_logistics_per_unit=_dec(v.inbound_logistics_per_unit),
                                    other_variable_cost_per_unit=_dec(v.other_variable_cost_per_unit)))
    settlements = list(session.scalars(select(Settlement).where(Settlement.shop_id == shop_id)))
    return ProfitInputs(shop_id=shop_id, currency=shop.currency, timezone=tz, orders=ctxs,
                        cost_versions=versions, settlements=settlements, fee_ratio_records=settled)


def load_current_rows(session: Any, order_ids: Sequence[int]) -> dict[int, Any]:
    if not order_ids:
        return {}
    rows = session.scalars(select(OrderProfitRow).where(OrderProfitRow.order_id.in_(order_ids),
                                                        OrderProfitRow.is_current.is_(True)))
    return {r.order_id: r for r in rows}


def compute_order_profits(session: Any, shop_id: int, since: date | None = None,
                          now: datetime | None = None) -> dict[str, Any]:
    """Full pipeline for one shop; commits. Returns counts + affected local dates."""
    now = now or datetime.now(UTC)
    inp = load_inputs(session, shop_id, since)
    calcs = compute_from_inputs(inp, now)
    current = load_current_rows(session, [c.order_id for c in calcs])
    stats = persist_order_profits(session, calcs, current, now)
    session.commit()
    dates = sorted({c.local_date for c in calcs})
    settled = sum(1 for c in calcs if not c.is_estimate)
    log.info("profit: shop=%s orders=%d settled=%d provisional=%d inserted=%d unchanged=%d",
             shop_id, len(calcs), settled, len(calcs) - settled, stats["inserted"], stats["unchanged"])
    return {**stats, "orders": len(calcs), "settled": settled, "provisional": len(calcs) - settled,
            "dates": dates}


__all__ = [
    "AD_WINDOW_DAYS", "PROVISIONAL_LABEL", "OrderCtx", "OrderProfitCalc", "ProfitInputs",
    "ad_deductions_by_day", "allocate_ads_blended", "build_items", "build_txns",
    "compute_from_inputs", "compute_order_profits", "estimate_provisional", "is_ad_deduction",
    "load_inputs", "local_date", "persist_order_profits", "record_to_dict", "row_from_calc",
    "snapshot_hash", "trailing_fee_ratio",
]
