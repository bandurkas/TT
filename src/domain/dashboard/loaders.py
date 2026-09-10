"""DB loaders for the dashboard (read-only, pre-aggregated tables; SPEC §55)."""


from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

ZERO_D = Decimal(0)

from src.db.models import (
    IntegrationSyncState,
    Order,
    OrderItem,
    Product,
    ProductMetric,
    Shop,
    ShopConfig,
    Video,
    VideoMetric,
)
from src.db.models import OrderProfit as OrderProfitRow
from src.db.models_finance import ShopMetric
from src.db.models_profit import ProductDaily, ShopDaily
from src.domain.dashboard.compute import FunnelCounts, Period
from src.domain.profit.jobs import DEFAULT_TZ, local_date


def shop_and_config(session: Any, shop_id: int | None) -> tuple[Any, Any]:
    shop = session.get(Shop, shop_id) if shop_id else session.scalars(select(Shop).order_by(Shop.id)).first()
    if shop is None:
        raise LookupError("no shop")
    cfg = session.scalar(select(ShopConfig).where(ShopConfig.shop_id == shop.id))
    return shop, cfg


def shop_daily(session: Any, shop_id: int, start: date, end: date) -> list[Any]:
    return list(session.scalars(select(ShopDaily).where(ShopDaily.shop_id == shop_id,
                                                        ShopDaily.metric_date >= start,
                                                        ShopDaily.metric_date <= end)
                                .order_by(ShopDaily.metric_date)))


def product_daily(session: Any, shop_id: int, start: date, end: date) -> list[Any]:
    return list(session.scalars(select(ProductDaily).join(Product, Product.id == ProductDaily.product_id)
                                .where(Product.shop_id == shop_id, ProductDaily.metric_date >= start,
                                       ProductDaily.metric_date <= end)))


def products(session: Any, shop_id: int) -> dict[int, Any]:
    return {p.id: p for p in session.scalars(select(Product).where(Product.shop_id == shop_id))}


def shop_funnel_by_day(session: Any, shop_id: int, start: date, end: date
                       ) -> dict[date, tuple[int, int, int]]:
    """(views, derived clicks = Σ views × ctr, video orders) per day from video_metrics. Product
    performance API carries no impressions/clicks (verified 2026-08-31): funnel = video traffic only."""
    q = (select(VideoMetric.metric_date, VideoMetric.views, VideoMetric.product_clicks, VideoMetric.ctr,
                VideoMetric.orders)
         .join(Video, Video.id == VideoMetric.video_id)
         .where(Video.shop_id == shop_id, VideoMetric.metric_hour.is_(None),
                VideoMetric.metric_date >= start, VideoMetric.metric_date <= end))
    out: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0])
    for d, views, clicks, ctr, orders in session.execute(q):
        v = int(views or 0)
        out[d][0] += v
        out[d][1] += int(clicks or 0) or int((Decimal(v) * Decimal(str(ctr or 0))).to_integral_value())
        out[d][2] += int(orders or 0)
    return {d: (a, b, c) for d, (a, b, c) in out.items()}


def product_funnel(session: Any, shop_id: int, start: date, end: date
                   ) -> dict[tuple[int, date], tuple[int, int, int]]:
    """Product-level (views, clicks, refunds) per day; views/clicks are 0 from this API (see above)."""
    q = (select(ProductMetric.product_id, ProductMetric.metric_date, ProductMetric.views,
                ProductMetric.clicks, ProductMetric.refunds)
         .join(Product, Product.id == ProductMetric.product_id)
         .where(Product.shop_id == shop_id, ProductMetric.sku_id.is_(None),
                ProductMetric.metric_date >= start, ProductMetric.metric_date <= end))
    return {(pid, d): (int(v or 0), int(c or 0), int(r or 0)) for pid, d, v, c, r in session.execute(q)}


def current_profits(session: Any, shop_id: int, start: date, end: date, tz: str
                    ) -> tuple[list[Any], dict[date, int], dict[date, int]]:
    """Current profit rows in period + refunded-order count per day + completed per day."""
    z = ZoneInfo(tz)
    lo = datetime.combine(start, datetime.min.time(), tzinfo=z)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=z)
    q = (select(OrderProfitRow, Order.order_created_at, Order.order_status)
         .join(Order, Order.id == OrderProfitRow.order_id)
         .where(Order.shop_id == shop_id, OrderProfitRow.is_current.is_(True),
                Order.order_created_at >= lo, Order.order_created_at < hi))
    rows, refunded, completed = [], defaultdict(int), defaultdict(int)
    for p, created, status in session.execute(q):
        d = local_date(created, tz)
        if d is None or not (start <= d <= end):
            continue
        rows.append(p)
        if str(p.profit_status) == "REFUNDED":
            refunded[d] += 1
        if str(status or "").upper() in ("COMPLETED", "DELIVERED"):
            completed[d] += 1
    return rows, dict(refunded), dict(completed)


def funnel_counts(session: Any, shop_id: int, period: Period, tz: str) -> FunnelCounts:
    f = shop_funnel_by_day(session, shop_id, period.start, period.end)
    rows, _, completed = current_profits(session, shop_id, period.start, period.end, tz)
    return FunnelCounts(impressions=sum(v for v, _, _ in f.values()), clicks=sum(c for _, c, _ in f.values()),
                        video_orders=sum(o for _, _, o in f.values()),
                        orders=len(rows), completed=sum(completed.values()),
                        settled=sum(1 for p in rows if str(p.profit_status) != "PROVISIONAL"))


def videos_with_metrics(session: Any, shop_id: int, start: date, end: date
                        ) -> tuple[dict[int, list[Any]], dict[int, Any]]:
    meta = {v.id: v for v in session.scalars(select(Video).where(Video.shop_id == shop_id))}
    daily: dict[int, list[Any]] = defaultdict(list)
    if meta:
        for m in session.scalars(select(VideoMetric).where(VideoMetric.video_id.in_(list(meta)),
                                                            VideoMetric.metric_date >= start,
                                                            VideoMetric.metric_date <= end,
                                                            VideoMetric.metric_hour.is_(None))):
            daily[m.video_id].append(m)
    return dict(daily), meta


def shop_metrics(session: Any, shop_id: int, start: date, end: date) -> list[Any]:
    return list(session.scalars(select(ShopMetric).where(ShopMetric.shop_id == shop_id,
                                                         ShopMetric.metric_date >= start,
                                                         ShopMetric.metric_date <= end)
                                .order_by(ShopMetric.metric_date)))


def last_sync(session: Any, shop_id: int) -> tuple[datetime | None, int | None]:
    t = session.scalar(select(func.max(IntegrationSyncState.last_successful_sync))
                       .where(IntegrationSyncState.shop_id == shop_id,
                              IntegrationSyncState.resource_type.in_(("orders", "statements"))))
    if t is None:
        return None, None
    return t, int((datetime.now(UTC) - t).total_seconds() // 60)


def cogs_gaps(session: Any, shop_id: int, start: date, end: date, tz: str) -> tuple[int, int]:
    """(orders with cogs_missing flag, distinct unmapped SKUs in order_items) for the period."""
    rows, _, _ = current_profits(session, shop_id, start, end, tz)
    missing = sum(1 for p in rows if (p.inputs_snapshot or {}).get("cogs_missing"))
    unmapped = session.scalar(select(func.count(func.distinct(OrderItem.id)))
                              .join(Order, Order.id == OrderItem.order_id)
                              .where(Order.shop_id == shop_id, OrderItem.sku_id.is_(None))) or 0
    return missing, int(unmapped)


def today_local(shop: Any) -> date:
    return local_date(datetime.now(UTC), shop.timezone or DEFAULT_TZ)  # type: ignore[return-value]


def ad_deductions(session: Any, shop_id: int, start: date, end: date, tz: str) -> list[dict[str, Any]]:
    from src.db.models import Settlement
    from src.domain.profit.jobs import is_ad_deduction
    out = []
    z = ZoneInfo(tz)
    lo = datetime.combine(start, datetime.min.time(), tzinfo=z)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=z)
    for s in session.scalars(select(Settlement).where(Settlement.shop_id == shop_id,
                                                      Settlement.settlement_at >= lo,
                                                      Settlement.settlement_at < hi)
                             .order_by(Settlement.settlement_at)):
        d = local_date(s.settlement_at, tz)
        if d and start <= d <= end and is_ad_deduction(s):
            out.append({"date": d, "settlement_id": s.external_settlement_id,
                        "amount": abs(Decimal(str(s.net_amount)))})
    return out


def affiliate_totals(profits: Sequence[Any]) -> dict[str, Any]:
    from src.domain.dashboard.orders import inputs_known
    aff = [p for p in profits if Decimal(str(p.affiliate_commission or 0)) != 0]
    commission = sum((Decimal(str(p.affiliate_commission)) for p in aff), Decimal(0))
    profit = sum((Decimal(str(p.estimated_net_profit)) for p in aff), Decimal(0))
    gmv = sum((Decimal(str(p.sale_proceeds)) for p in aff), Decimal(0))
    return {"orders": len(aff), "gmv": gmv, "affiliate_commission": commission,
            "profit_after_commission": profit if all(inputs_known(p) and (p.inputs_snapshot or {}).get("ad_cost_known") for p in aff) else None}


def video_product_metrics(session: Any, shop_id: int, start: date, end: date) -> list[Any]:
    from src.db.models import VideoProductMetric
    return list(session.scalars(select(VideoProductMetric).join(Video, Video.id == VideoProductMetric.video_id)
                                .where(Video.shop_id == shop_id, VideoProductMetric.metric_date >= start,
                                       VideoProductMetric.metric_date <= end)))


def campaign_spend(session: Any, shop_id: int, start: date, end: date) -> list[dict[str, Any]]:
    """Per-campaign GMV Max Cost from the Ads API (SPEC §5.14 ad_metrics).

    `orders` / `revenue` here are TikTok's own attribution, not the shop's (SPEC §7): they answer
    "what did the platform credit this campaign with", never "what did the shop actually book".
    They are returned alongside Cost precisely so the two are not confused for one another.
    """
    from src.db.models import AdAccount, AdMetric, Campaign

    rows = session.execute(
        select(Campaign.external_campaign_id, Campaign.name,
               func.sum(AdMetric.spend), func.sum(AdMetric.attributed_orders),
               func.sum(AdMetric.attributed_gmv), func.max(AdMetric.fetched_at),
               func.bool_and(AdMetric.is_final))
        .join(AdMetric, (AdMetric.entity_type == "campaign") & (AdMetric.entity_id == Campaign.id))
        .join(AdAccount, AdAccount.id == Campaign.ad_account_id)
        .where(AdAccount.shop_id == shop_id, AdMetric.metric_date >= start,
               AdMetric.metric_date <= end, AdMetric.metric_hour.is_(None))
        .group_by(Campaign.external_campaign_id, Campaign.name)).all()

    out = []
    for ext_id, name, spend, orders, gmv, fetched, final in rows:
        spend = Decimal(str(spend or 0))
        orders = int(orders or 0)
        gmv = Decimal(str(gmv or 0))
        if not spend and not orders:
            continue   # a campaign that did nothing in this period is noise, not a zero worth showing
        out.append({"campaign_id": ext_id, "name": name or ext_id, "spend": spend,
                    "attributed_orders": orders, "attributed_revenue": gmv,
                    # Cost per order and ROI as the platform reports them; both are undefined
                    # without orders, and a zero would read as "free", so they stay null.
                    "cost_per_order": (spend / orders).quantize(Decimal(1)) if orders else None,
                    "reported_roi": (gmv / spend).quantize(Decimal("0.01")) if spend else None,
                    "final": bool(final), "fetched_at": fetched})
    out.sort(key=lambda r: -r["spend"])
    return out


def _verdict(contribution: Decimal, spend: Decimal, orders: int) -> dict[str, Any]:
    """How much room a product has before its next order stops paying.

    headroom = break-even CPO / actual CPO. Above 1 the product can absorb more spend per order and
    still earn; below 1 every additional order is bought at a loss. It is deliberately a ratio: a
    single shop-wide CPO target cannot serve a 19,000 single pair and a 75,000 five-pack at once.
    """
    if spend and not orders:
        return {"headroom": None, "verdict": "no_orders"}
    if not orders or not spend:
        return {"headroom": None, "verdict": "no_data"}
    be, cpo = contribution / orders, spend / orders
    if cpo <= 0:
        return {"headroom": None, "verdict": "no_data"}
    h = (be / cpo).quantize(Decimal("0.01"))
    return {"headroom": h, "verdict": "scale" if h >= Decimal("1.2")
            else "hold" if h >= Decimal("0.9") else "cut"}


def creative_bridge(session: Any, shop_id: int, start: date, end: date) -> dict[str, Any]:
    """Video -> product -> measured ad Cost. The only honest chain from a creative to money.

    GMV Max does not attribute spend to a video (96% of orders land in its unattributed bucket,
    measured 2026-09-09), so per-video ROI does not exist and is not invented here. What does exist:
    a video promotes products, and each product's advertising is measured exactly. A creative is
    therefore judged on how well it converts attention (organic GPM/CTR) and on whether the product
    it carries earns its ad money.
    """
    from src.db.models import AdMetric, Product, Video, VideoMetric, VideoProduct
    from src.db.models_profit import ProductDaily

    spend_rows = dict(session.execute(
        select(AdMetric.entity_id, func.sum(AdMetric.spend))
        .where(AdMetric.entity_type == "product", AdMetric.metric_date >= start,
               AdMetric.metric_date <= end, AdMetric.metric_hour.is_(None))
        .group_by(AdMetric.entity_id)).all())

    prod = {}
    for pid, ext, title, orders, units, rev, cogs, contrib in session.execute(
            select(Product.id, Product.external_product_id, Product.title,
                   func.sum(ProductDaily.orders), func.sum(ProductDaily.units),
                   func.sum(ProductDaily.net_seller_revenue), func.sum(ProductDaily.cogs),
                   func.sum(ProductDaily.contribution))
            .join(ProductDaily, ProductDaily.product_id == Product.id)
            .where(Product.shop_id == shop_id, ProductDaily.metric_date >= start,
                   ProductDaily.metric_date <= end)
            .group_by(Product.id, Product.external_product_id, Product.title)).all():
        contrib = Decimal(str(contrib or 0))
        spend = Decimal(str(spend_rows.get(pid, 0)))
        orders = int(orders or 0)
        prod[pid] = {"product_id": pid, "external_product_id": ext, "title": title,
                     "orders": orders, "units": int(units or 0),
                     "revenue": Decimal(str(rev or 0)), "cogs": Decimal(str(cogs or 0)),
                     "contribution": contrib, "ad_cost": spend, "profit": contrib - spend,
                     # What one more order may cost before it stops paying. Varies enormously by
                     # product (a 19,000 single pair against a 75,000 five-pack), which is exactly
                     # why one shop-wide CPO target misleads.
                     "break_even_cpo": (contrib / orders).quantize(Decimal(1)) if orders else None,
                     "cpo": (spend / orders).quantize(Decimal(1)) if orders else None,
                     **_verdict(contrib, spend, orders)}
    # Ad money on products with no sales in the window is still money; it is listed, not spread.
    for pid, amount in spend_rows.items():
        if pid not in prod:
            p = session.get(Product, pid)
            spend = Decimal(str(amount))
            prod[pid] = {"product_id": pid, "external_product_id": getattr(p, "external_product_id", None),
                         "title": getattr(p, "title", str(pid)), "orders": 0, "units": 0,
                         "revenue": ZERO_D, "cogs": ZERO_D, "contribution": ZERO_D,
                         "ad_cost": spend, "profit": -spend, "break_even_cpo": None, "cpo": None,
                         **_verdict(ZERO_D, spend, 0)}

    vids = {}
    for vid, ext_v, caption, views, clicks, orders, gmv in session.execute(
            select(Video.id, Video.external_video_id, Video.caption,
                   func.sum(VideoMetric.views), func.sum(VideoMetric.product_clicks),
                   func.sum(VideoMetric.orders), func.sum(VideoMetric.gmv))
            .join(VideoMetric, VideoMetric.video_id == Video.id)
            .where(VideoMetric.metric_date >= start, VideoMetric.metric_date <= end)
            .group_by(Video.id, Video.external_video_id, Video.caption)).all():
        views, gmv = int(views or 0), Decimal(str(gmv or 0))
        vids[vid] = {"video_id": vid, "external_video_id": ext_v, "caption": caption,
                     "views": views, "clicks": int(clicks or 0), "orders": int(orders or 0),
                     "gmv": gmv,
                     # GMV per 1000 views: how well the creative turns attention into money,
                     # independent of who paid for the attention.
                     "gpm": (gmv / views * 1000).quantize(Decimal(1)) if views else None,
                     "products": []}

    for vid, pid in session.execute(
            select(VideoProduct.video_id, VideoProduct.product_id)).all():
        if vid in vids and pid in prod:
            vids[vid]["products"].append(pid)

    return {"products": sorted(prod.values(), key=lambda r: -r["ad_cost"]),
            "videos": sorted(vids.values(), key=lambda r: -(r["gpm"] or 0))}
