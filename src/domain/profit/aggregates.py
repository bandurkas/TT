"""Daily shop / product aggregates from current analytics_order_profit rows (+ shop_metrics GMV)."""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from src.analytics.attribution import allocate_proportionally
from src.analytics.profitability import ProfitStatus
from src.db.models import Order, Product
from src.db.models import OrderProfit as OrderProfitRow
from src.db.models_finance import ShopMetric
from src.db.models_profit import ProductDaily, ShopDaily
from src.domain.ingest.upserts import upsert
from src.domain.profit.jobs import DEFAULT_TZ, local_date

log = logging.getLogger("tt.profit.aggregates")
ZERO = Decimal(0)
RATIO_PLACES = Decimal("0.000001")


def _d(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v)) if v is not None else ZERO


@dataclass
class DailyAgg:
    orders: int = 0
    units: int = 0
    gmv: Decimal = ZERO
    net_seller_revenue: Decimal = ZERO
    fees: Decimal = ZERO
    affiliate: Decimal = ZERO
    cogs: Decimal = ZERO
    contribution: Decimal = ZERO
    ad_cost: Decimal = ZERO
    net_profit: Decimal = ZERO
    refunds: Decimal = ZERO
    settled_orders: int = 0
    provisional_orders: int = 0
    _seen: set[Any] = field(default_factory=set, repr=False)

    @property
    def net_margin(self) -> Decimal | None:
        if self.net_seller_revenue <= ZERO:
            return None
        return (self.net_profit / self.net_seller_revenue).quantize(RATIO_PLACES)

    def as_row(self, computed_at: datetime, gmv_override: Decimal | None = None) -> dict[str, Any]:
        return {
            "orders": self.orders, "units": self.units,
            "gmv": gmv_override if gmv_override is not None else self.gmv,
            "net_seller_revenue": self.net_seller_revenue, "fees": self.fees,
            "affiliate": self.affiliate, "cogs": self.cogs, "contribution": self.contribution,
            "ad_cost": self.ad_cost, "net_profit": self.net_profit, "net_margin": self.net_margin,
            "refunds": self.refunds, "settled_orders": self.settled_orders,
            "provisional_orders": self.provisional_orders, "computed_at": computed_at,
        }


def _add_order(a: DailyAgg, p: Any) -> None:
    a.orders += 1
    a.net_seller_revenue += _d(p.net_seller_revenue)
    a.fees += _d(p.platform_fees) + _d(p.seller_shipping) + _d(p.taxes)
    a.affiliate += _d(p.affiliate_commission)
    a.cogs += _d(p.cogs) + _d(p.packaging) + _d(p.inbound_logistics) + _d(p.other_variable)
    a.contribution += _d(p.contribution_profit)
    a.ad_cost += _d(p.allocated_ad_cost)
    a.net_profit += _d(p.estimated_net_profit)
    a.refunds += _d(p.refunds)
    a.gmv += _d(p.sale_proceeds)
    if p.profit_status == ProfitStatus.PROVISIONAL:
        a.provisional_orders += 1
    else:
        a.settled_orders += 1
    a.units += sum(int(i.get("quantity") or 0) for i in (p.inputs_snapshot or {}).get("items", []))


def shop_daily(profits: Iterable[Any], order_dates: Mapping[int, date]) -> dict[date, DailyAgg]:
    """profits: current OrderProfit rows; order_dates: order_id -> shop-local order date."""
    out: dict[date, DailyAgg] = defaultdict(DailyAgg)
    for p in profits:
        d = order_dates.get(p.order_id)
        if d is None:
            continue
        _add_order(out[d], p)
    return dict(out)


def product_daily(profits: Iterable[Any], order_dates: Mapping[int, date]) -> dict[tuple[int, date], DailyAgg]:
    """Per product per day from the per-item split stored in inputs_snapshot['items'].
    Fees/affiliate/refunds are not split per item by the engine -> spread by gross_item_value share
    via allocate_proportionally (sum over items == order value exactly)."""
    out: dict[tuple[int, date], DailyAgg] = defaultdict(DailyAgg)
    for p in profits:
        d = order_dates.get(p.order_id)
        items = (p.inputs_snapshot or {}).get("items", [])
        if d is None or not items:
            continue
        fees = _d(p.platform_fees) + _d(p.seller_shipping) + _d(p.taxes)
        prov = p.profit_status == ProfitStatus.PROVISIONAL
        weights = {str(n): _d(i.get("gross_item_value")) for n, i in enumerate(items)}
        cur = getattr(p, "currency", None) or "IDR"
        split = {k: allocate_proportionally(v, weights, cur)
                 for k, v in (("fees", fees), ("aff", _d(p.affiliate_commission)),
                              ("ref", _d(p.refunds)))}
        for n, i in enumerate(items):
            pid = i.get("product_id")
            if pid is None:
                continue
            a = out[(int(pid), d)]
            key = (p.order_id, p.id if hasattr(p, "id") else None)
            if key not in a._seen:
                a._seen.add(key)
                a.orders += 1
                a.settled_orders += 0 if prov else 1
                a.provisional_orders += 1 if prov else 0
            a.units += int(i.get("quantity") or 0)
            a.gmv += _d(i.get("gross_item_value"))
            a.net_seller_revenue += _d(i.get("net_seller_revenue"))
            a.cogs += _d(i.get("cogs"))
            a.ad_cost += _d(i.get("allocated_ad_cost"))
            a.net_profit += _d(i.get("estimated_net_profit"))
            a.contribution += _d(i.get("net_seller_revenue")) - _d(i.get("cogs"))
            a.fees += split["fees"][str(n)]
            a.affiliate += split["aff"][str(n)]
            a.refunds += split["ref"][str(n)]
    return dict(out)


# --- DB ---------------------------------------------------------------------------------------
def load_current_profits(session: Any, shop_id: int, dates: Sequence[date] | None, tz: str
                         ) -> tuple[list[Any], dict[int, date]]:
    q = (select(OrderProfitRow, Order.order_created_at).join(Order, Order.id == OrderProfitRow.order_id)
         .where(Order.shop_id == shop_id, OrderProfitRow.is_current.is_(True)))
    profits, order_dates = [], {}
    for p, created in session.execute(q):
        d = local_date(created, tz)
        if d is None or (dates and d not in dates):
            continue
        profits.append(p)
        order_dates[p.order_id] = d
    return profits, order_dates


def load_gmv(session: Any, shop_id: int, dates: Sequence[date]) -> dict[date, Decimal]:
    if not dates:
        return {}
    rows = session.execute(select(ShopMetric.metric_date, ShopMetric.gmv_total)
                           .where(ShopMetric.shop_id == shop_id, ShopMetric.metric_date.in_(dates)))
    return {d: _d(g) for d, g in rows if g is not None}


def recompute_daily(session: Any, shop_id: int, dates: Sequence[date] | None = None,
                    tz: str = DEFAULT_TZ, now: datetime | None = None) -> dict[str, int]:
    """Recompute analytics_shop_daily / analytics_product_daily for the given local dates
    (None = every date that has a current profit row). Commits."""
    now = now or datetime.now(UTC)
    profits, order_dates = load_current_profits(session, shop_id, dates, tz)
    days = sorted(set(order_dates.values()) | set(dates or []))
    gmv = load_gmv(session, shop_id, days)
    shop_rows = shop_daily(profits, order_dates)
    rows = [{"shop_id": shop_id, "metric_date": d,
             **shop_rows.get(d, DailyAgg()).as_row(now, gmv.get(d))} for d in days]
    upsert(session, ShopDaily, rows, ["shop_id", "metric_date"])
    prows = [{"product_id": pid, "metric_date": d, **a.as_row(now)}
             for (pid, d), a in product_daily(profits, order_dates).items()]
    if days:  # stale rows (product no longer sold that day after recompute) must not linger
        shop_products = select(Product.id).where(Product.shop_id == shop_id)
        session.execute(delete(ProductDaily).where(ProductDaily.product_id.in_(shop_products),
                                                   ProductDaily.metric_date.in_(days)))
    upsert(session, ProductDaily, prows, ["product_id", "metric_date"])
    session.commit()
    log.info("aggregates: shop=%s days=%d product_rows=%d", shop_id, len(rows), len(prows))
    return {"shop_days": len(rows), "product_rows": len(prows)}


__all__ = ["DailyAgg", "product_daily", "recompute_daily", "shop_daily"]
