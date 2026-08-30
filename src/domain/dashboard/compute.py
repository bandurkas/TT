"""Pure dashboard computations over pre-aggregated rows (Decimal only). No DB, no LLM."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.analytics.anomaly_detection import (
    FunnelDiagnosis,
    FunnelStage,
    detect_funnel_deterioration,
)
from src.analytics.creative_scoring import (
    Classification,
    ScoringBaselines,
    ScoringConfig,
    VideoMetrics,
    classify_video,
    median,
)
from src.analytics.data_quality import DataQuality, DataQualityInputs, DQState, compute_data_quality

ZERO = Decimal(0)
PCT = Decimal("0.0001")
RATIO = Decimal("0.01")
NOT_AVAILABLE = "NOT_AVAILABLE"  # SPEC §38: unavailable field = explicit, never a guess

DAILY_FIELDS = ("orders", "units", "gmv", "net_seller_revenue", "fees", "affiliate", "cogs",
                "contribution", "ad_cost", "net_profit", "refunds", "settled_orders", "provisional_orders")


def _d(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v)) if v is not None else ZERO


def ratio(num: Decimal | int, den: Decimal | int, places: Decimal = PCT) -> Decimal | None:
    num, den = _d(num), _d(den)
    return (num / den).quantize(places) if den else None


def pct_change(cur: Decimal | None, prev: Decimal | None) -> Decimal | None:
    if cur is None or prev is None or prev == ZERO:
        return None
    return ((cur - prev) / abs(prev)).quantize(PCT)


def normalize(obj: Any) -> Any:
    """Decimal -> exponent-free string (25000 not 25000.000000); recurses into dict/list."""
    if isinstance(obj, Decimal):
        return format(obj.normalize() if obj != ZERO else ZERO, "f")
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize(v) for v in obj]
    return obj


def clamp(v: Decimal, lo: Decimal = ZERO, hi: Decimal = Decimal(100)) -> int:
    return int(max(lo, min(hi, v)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class Period:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> Period:
        return Period(self.start - timedelta(days=self.days), self.start - timedelta(days=1))


def default_periods(today: date, start: date | None = None, end: date | None = None,
                    cmp_start: date | None = None, cmp_end: date | None = None) -> tuple[Period, Period]:
    end = end or today
    start = start or end.replace(day=1)
    if start > end:
        start, end = end, start
    cur = Period(start, end)
    cmp = Period(cmp_start, cmp_end) if cmp_start and cmp_end else cur.previous()
    return cur, cmp


# --- totals -------------------------------------------------------------------------------------
@dataclass
class Totals:
    profit_inputs_known: bool = True
    ad_cost_known: bool = True
    ad_cost_partial: bool = False
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
    refunded_orders: int = 0
    clicks: int = 0
    impressions: int = 0
    video_orders: int = 0  # orders attributed by the video analytics API (video traffic only)
    days_with_data: int = 0

    @property
    def net_margin(self) -> Decimal | None:
        return ratio(self.net_profit, self.net_seller_revenue) if self.profit_known and self.net_seller_revenue > 0 else None

    @property
    def profit_known(self):
        return self.ad_cost_known and self.profit_inputs_known

    @property
    def blended_roas(self) -> Decimal | None:
        return ratio(self.net_seller_revenue, self.ad_cost, RATIO) if self.ad_cost_known and self.ad_cost > 0 else None

    @property
    def aov(self) -> Decimal | None:
        return (self.gmv / self.orders).quantize(Decimal(1)) if self.orders else None

    @property
    def cvr(self) -> Decimal | None:
        """Video CVR: video-attributed orders / derived clicks (product-card traffic has no clicks)."""
        return ratio(self.video_orders, self.clicks) if self.clicks else None

    @property
    def ctr(self) -> Decimal | None:
        return ratio(self.clicks, self.impressions) if self.impressions else None

    @property
    def refund_rate(self) -> Decimal | None:
        return ratio(self.refunded_orders, self.orders) if self.orders else None

    @property
    def settlement_coverage(self) -> Decimal | None:
        n = self.settled_orders + self.provisional_orders
        return ratio(self.settled_orders, n) if n else None

    @property
    def contribution_ratio(self) -> Decimal | None:
        return ratio(self.contribution, self.net_seller_revenue) if self.profit_inputs_known and self.net_seller_revenue > 0 else None

    @property
    def break_even_roas(self) -> Decimal | None:
        """Ad spend per net-revenue unit that leaves zero profit: 1 / contribution ratio."""
        c = self.contribution_ratio
        return (Decimal(1) / c).quantize(RATIO) if c and c > 0 else None


def sum_daily(rows: Iterable[Any], period: Period, funnel: Mapping[date, tuple[int, int, int]] | None = None,
              refunded: Mapping[date, int] | None = None) -> Totals:
    """funnel: day -> (video views, derived clicks, video orders)."""
    t = Totals()
    for r in rows:
        d = r.metric_date
        if not (period.start <= d <= period.end):
            continue
        t.days_with_data += 1
        t.profit_inputs_known = t.profit_inputs_known and bool(getattr(r, "profit_inputs_known", True))
        for f in DAILY_FIELDS:
            v = getattr(r, f, 0) or 0
            setattr(t, f, getattr(t, f) + (int(v) if isinstance(getattr(t, f), int) else _d(v)))
    for d in (funnel or {}):
        if period.start <= d <= period.end:
            imp, clk, vo = funnel[d]  # type: ignore[index]
            t.impressions += imp
            t.clicks += clk
            t.video_orders += vo
    for d, n in (refunded or {}).items():
        if period.start <= d <= period.end:
            t.refunded_orders += n
    return t


# --- KPI cards ------------------------------------------------------------------------------------
GOOD, WARN, BAD, NEUTRAL = "good", "warn", "bad", "neutral"


def _status(value: Decimal | None, good_if: str, threshold: Decimal | None = None) -> str:
    if value is None:
        return NEUTRAL
    if threshold is None:
        return GOOD if (value > 0) == (good_if == "up") or value == 0 else BAD
    if good_if == "up":
        return GOOD if value >= threshold else BAD
    return GOOD if value <= threshold else BAD


def kpi(key: str, value: Decimal | int | None, prev: Decimal | int | None, spark: Sequence[Decimal],
        *, kind: str = "money", status: str = NEUTRAL, note: str | None = None,
        provisional: bool = False, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    v = _d(value) if value is not None else None
    p = _d(prev) if prev is not None else None
    return {"key": key, "kind": kind, "value": v, "prev": p,
            "change_abs": (v - p) if v is not None and p is not None else None,
            "change_pct": pct_change(v, p), "sparkline": list(spark), "status": status,
            "note": note, "provisional": provisional, "meta": meta or {}}


def sparkline(rows: Iterable[Any], end: date, field_: str, n: int = 7) -> list[Decimal]:
    by = {r.metric_date: _d(getattr(r, field_, 0) or 0) for r in rows}
    return [by.get(end - timedelta(days=k), ZERO) for k in range(n - 1, -1, -1)]


def business_health(cur: Totals, prev: Totals, daily_rows: Sequence[Any], period: Period,
                    floor_margin: Decimal, dq: DataQuality) -> dict[str, Any]:
    prov = cur.provisional_orders > 0 or cur.ad_cost_partial or not cur.ad_cost_known
    m, pm = cur.net_margin, prev.net_margin
    cards = [
        kpi("net_profit", cur.net_profit if cur.profit_known else None,
            prev.net_profit if prev.profit_known else None, [],
            status=_status(cur.net_profit, "up") if cur.profit_known else NEUTRAL, provisional=prov,
            note="accrual; ad cost BLENDED estimate" if cur.ad_cost else "accrual"),
        kpi("gmv", cur.gmv, prev.gmv, sparkline(daily_rows, period.end, "gmv"),
            status=_status(pct_change(cur.gmv, prev.gmv), "up"), note=f"{cur.units} units",
            meta={"units": cur.units}),
        kpi("net_seller_revenue", cur.net_seller_revenue, prev.net_seller_revenue,
            sparkline(daily_rows, period.end, "net_seller_revenue"),
            status=_status(pct_change(cur.net_seller_revenue, prev.net_seller_revenue), "up"),
            note="after fees & refunds", provisional=prov),
        kpi("orders", cur.orders, prev.orders, sparkline(daily_rows, period.end, "orders"), kind="count",
            status=_status(pct_change(Decimal(cur.orders), Decimal(prev.orders)), "up"),
            note=f"{cur.refunded_orders} refunded", meta={"refunded": cur.refunded_orders}),
        kpi("ad_spend", cur.ad_cost if cur.ad_cost_known else None,
            prev.ad_cost if prev.ad_cost_known else None, [],
            status=NEUTRAL, provisional=cur.ad_cost_partial or not cur.ad_cost_known,
            note=(f"{ratio(cur.ad_cost, cur.net_seller_revenue)!s} of net revenue"
                  if cur.net_seller_revenue > 0 and cur.ad_cost_known else "Advertising report incomplete"),
            meta={"ad_share": ratio(cur.ad_cost, cur.net_seller_revenue) if cur.ad_cost_known and cur.net_seller_revenue > 0 else None}),
        kpi("net_margin", m, pm, [], kind="pct", status=_status(m, "up", floor_margin),
            note=f"floor {floor_margin}", provisional=prov, meta={"floor": floor_margin}),
        kpi("reported_roas", None, None, [], kind="ratio", status=NEUTRAL, note=NOT_AVAILABLE + ": Ads API"),
        kpi("blended_roas", cur.blended_roas, prev.blended_roas, [], kind="ratio",
            status=_status(cur.blended_roas, "up", cur.break_even_roas) if cur.break_even_roas else NEUTRAL,
            note=f"break-even {cur.break_even_roas}" if cur.break_even_roas else "net revenue / ad spend",
            provisional=True, meta={"break_even": cur.break_even_roas}),
        kpi("aov", cur.aov, prev.aov, [], status=_status(pct_change(cur.aov, prev.aov), "up")),
        kpi("cvr", cur.cvr, prev.cvr, [], kind="pct", status=_status(pct_change(cur.cvr, prev.cvr), "up"),
            note=f"video CVR: {cur.video_orders} video orders / derived clicks", provisional=True),
        kpi("refund_rate", cur.refund_rate, prev.refund_rate, [], kind="pct",
            status=_status(cur.refund_rate, "down", Decimal("0.10")), note="refunded orders / orders"),
        kpi("settlement_coverage", cur.settlement_coverage, prev.settlement_coverage, [], kind="pct",
            status=_status(cur.settlement_coverage, "up", Decimal("0.90")),
            note=f"{cur.provisional_orders} provisional",
            meta={"settled": cur.settled_orders, "provisional": cur.provisional_orders}),
    ]
    return {"cards": cards, "health": profit_health(cur, prev, floor_margin, dq),
            "unit_economics": unit_economics(cur)}


def profit_health(cur: Totals, prev: Totals, floor: Decimal, dq: DataQuality) -> dict[str, Any]:
    """Deterministic 0-100 (SPEC §42.1): mean of components, each explained."""
    comp: dict[str, int | None] = {}
    m = cur.net_margin
    comp["margin"] = None if m is None else clamp(50 + 50 * (m - floor) / floor) if floor else None
    r, be = cur.blended_roas, cur.break_even_roas
    comp["ad_efficiency"] = None if r is None or be is None else clamp(50 + 50 * (r - be) / be)
    ch = pct_change(cur.cvr, prev.cvr)
    comp["conversion"] = None if cur.cvr is None else 50 if ch is None else clamp(50 + 50 * ch / Decimal("0.3"))
    rr = cur.refund_rate
    comp["refunds"] = None if rr is None else clamp(100 - rr / Decimal("0.15") * 50)
    comp["data_quality"] = dq.score
    known = [v for v in comp.values() if v is not None]
    score = clamp(Decimal(sum(known)) / len(known)) if known else 0
    grade = "GOOD" if score >= 75 else "FAIR" if score >= 50 else "POOR"
    return {"score": score, "grade": grade, "components": comp}


def unit_economics(t: Totals) -> dict[str, Any] | None:
    if not t.units:
        return None
    u = Decimal(t.units)
    q = lambda v: (v / u).quantize(Decimal(1))
    # All rows use the same order-profit basis; Shop Analytics GMV is a different data source.
    rev = q(t.net_seller_revenue + t.fees + t.affiliate)
    fees = q(t.fees + t.affiliate)
    cogs = q(t.cogs)
    ads = q(t.ad_cost)
    difference = t.net_seller_revenue - t.cogs - t.ad_cost - t.net_profit
    contribution_difference = t.net_seller_revenue - t.cogs - t.contribution
    return {"units": t.units, "revenue_per_unit": rev, "fees_per_unit": fees if t.profit_inputs_known else None, "cogs_per_unit": cogs if t.profit_inputs_known else None,
            "contribution_per_unit": q(t.contribution) if t.profit_inputs_known else None, "ad_cost_per_unit": ads if t.ad_cost_known else None,
            "net_per_unit": q(t.net_profit) if t.profit_known else None, "ad_cost_is_estimate": True,
            "revenue_basis": "after_refunds_and_adjustments_before_fees",
            "calculation_difference": difference,
            "contribution_difference": contribution_difference,
            "contribution_rounding_per_unit": q(t.contribution) - (rev - fees - cogs)
            if difference == ZERO and contribution_difference == ZERO else None,
            "rounding_per_unit": q(t.net_profit) - (q(t.contribution) - ads)
            if difference == ZERO and contribution_difference == ZERO else None}


# --- trends -------------------------------------------------------------------------------------
def trend_series(rows: Iterable[Any], period: Period) -> list[dict[str, Any]]:
    by = {r.metric_date: r for r in rows if period.start <= r.metric_date <= period.end}
    out, cum, complete = [], ZERO, True
    for k in range(period.days):
        d = period.start + timedelta(days=k)
        r = by.get(d)
        known = bool(getattr(r, "ad_cost_known", False)) if r else False
        profit_known = known and bool(getattr(r, "profit_inputs_known", False))
        complete = complete and profit_known
        np_ = _d(getattr(r, "net_profit", 0)) if r else ZERO
        cum += np_
        out.append({"date": d, "gmv": _d(getattr(r, "gmv", 0)) if r else ZERO,
                    "net_seller_revenue": _d(getattr(r, "net_seller_revenue", 0)) if r else ZERO,
                    "ad_cost": _d(r.ad_cost) if known else None, "net_profit": np_ if profit_known else None,
                    "cum_net_profit": cum if complete else None, "orders": int(getattr(r, "orders", 0) or 0) if r else 0,
                    "settled_orders": int(getattr(r, "settled_orders", 0) or 0) if r else 0,
                    "provisional_orders": int(getattr(r, "provisional_orders", 0) or 0) if r else 0})
    return out


# --- products -------------------------------------------------------------------------------------
PRODUCT_STATUS = {"SCALE": "SCALE", "HEALTHY": "HEALTHY", "WATCH": "WATCH", "INVESTIGATE": "INVESTIGATE",
                  "REDUCE": "REDUCE", "SMALL_SAMPLE": "SMALL_SAMPLE"}


def product_status(t: Totals, floor: Decimal, min_orders: int) -> tuple[str, str]:
    if not t.profit_known or t.ad_cost_partial or t.provisional_orders:
        return "INVESTIGATE", "profit inputs missing or preliminary; verify before changing spend"
    if t.orders < min_orders:
        return "SMALL_SAMPLE", f"{t.orders} orders < {min_orders}"
    m = t.net_margin
    if m is None:
        return "SMALL_SAMPLE", "no net revenue"
    if t.net_profit < 0:
        return "REDUCE", f"net loss {t.net_profit}"
    if m < floor:
        return "INVESTIGATE", f"margin {m} below floor {floor}"
    if m >= 2 * floor and t.orders >= 2 * min_orders:
        return "SCALE", f"margin {m} ≥ 2× floor on {t.orders} orders"
    return "HEALTHY", f"margin {m}"


def product_rows(product_daily: Iterable[Any], product_meta: Mapping[int, Any], period: Period,
                 pm_funnel: Mapping[tuple[int, date], tuple[int, int, int]], floor: Decimal,
                 min_orders: int) -> list[dict[str, Any]]:
    """product_daily rows (per product per day) -> table rows for the period; sorted by net profit."""
    per: dict[int, Totals] = {}
    for r in product_daily:
        if not (period.start <= r.metric_date <= period.end):
            continue
        t = per.setdefault(r.product_id, Totals())
        t.profit_inputs_known = t.profit_inputs_known and bool(getattr(r, "profit_inputs_known", False))
        t.ad_cost_known = t.ad_cost_known and bool(getattr(r, "ad_cost_known", False))
        t.ad_cost_partial = t.ad_cost_partial or bool(getattr(r, "ad_cost_partial", False))
        for f in DAILY_FIELDS:
            v = getattr(r, f, 0) or 0
            setattr(t, f, getattr(t, f) + (int(v) if isinstance(getattr(t, f), int) else _d(v)))
    for (pid, d), (imp, clk, ref) in pm_funnel.items():
        if period.start <= d <= period.end and pid in per:
            per[pid].impressions += imp
            per[pid].clicks += clk
            per[pid].refunded_orders += ref
    out = []
    for pid, t in per.items():
        st, why = product_status(t, floor, min_orders)
        meta = product_meta.get(pid)
        out.append({"product_id": pid, "title": getattr(meta, "title", None) or f"product {pid}",
                    "external_product_id": getattr(meta, "external_product_id", None),
                    "units": t.units, "orders": t.orders, "gmv": t.gmv,
                    "net_seller_revenue": t.net_seller_revenue, "fees": t.fees, "affiliate": t.affiliate,
                    "cogs": t.cogs, "ad_cost": t.ad_cost if t.ad_cost_known else None, "ad_cost_is_estimate": True,
                    "refunds": t.refunds, "net_profit": t.net_profit if t.profit_known else None, "net_margin": t.net_margin,
                    "cvr": None, "ctr": None, "cvr_note": NOT_AVAILABLE + ": product clicks not in Shop API",
                    "status": st, "status_reason": why})
    out.sort(key=lambda r: (r["net_profit"] is not None, r["net_profit"] or ZERO), reverse=True)
    return out


# --- videos -------------------------------------------------------------------------------------
def _pub_date(meta: Any, tz: str | None) -> date | None:
    pub = getattr(meta, "published_at", None)
    if pub is None:
        return None
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=UTC)
    if tz:
        from zoneinfo import ZoneInfo
        return pub.astimezone(ZoneInfo(tz)).date()
    return pub.date()


def video_cards(video_daily: Mapping[int, Sequence[Any]], video_meta: Mapping[int, Any], period: Period,
                today: date, cfg: ScoringConfig, tz: str | None = None) -> list[dict[str, Any]]:
    """video_metrics rows grouped by video -> classified cards (creative_scoring). Ad spend per video
    is NOT AVAILABLE (Ads API) -> classification uses traffic/orders only; net_profit unknown -> 0."""
    agg: dict[int, dict[str, Any]] = {}
    for vid, rows in video_daily.items():
        imp = clk = orders = 0
        measured = derived = 0
        gmv = ZERO
        views = 0
        for r in rows:
            if not (period.start <= r.metric_date <= period.end):
                continue
            v = int(r.views or 0)
            imp += v  # CTR base = views (API's click_through_rate is clicks/views)
            if int(r.product_clicks or 0):
                clk += int(r.product_clicks)
                measured += 1
            else:
                clk += int((Decimal(v) * _d(r.ctr)).to_integral_value())
                derived += 1
            orders += int(r.orders or 0)
            views += int(r.views or 0)
            gmv += _d(r.gmv)
        if imp == clk == orders == views == 0:
            continue
        agg[vid] = {"impressions": imp, "clicks": clk, "orders": orders, "gmv": gmv, "views": views,
                    "clicks_measured_days": measured, "clicks_derived_days": derived}
    ctrs = [ratio(a["clicks"], a["impressions"]) for a in agg.values() if a["impressions"]]
    cvrs = [ratio(a["orders"], a["clicks"]) for a in agg.values() if a["clicks"]]
    base = ScoringBaselines(account_median_ctr=median([c for c in ctrs if c is not None]),
                            account_median_cvr=median([c for c in cvrs if c is not None]))
    out = []
    for vid, a in agg.items():
        meta = video_meta.get(vid)
        pub = getattr(meta, "published_at", None)
        pday = _pub_date(meta, tz)
        age = max(1, (today - pday).days) if pday else 1
        res = classify_video(VideoMetrics(video_id=str(vid), impressions=a["impressions"], clicks=a["clicks"],
                                          orders=a["orders"], gmv=a["gmv"], age_days=age), base, cfg)
        out.append({"video_id": vid, "external_video_id": getattr(meta, "external_video_id", None),
                    "caption": getattr(meta, "caption", None), "published_at": pub,
                    "duration_seconds": getattr(meta, "duration_seconds", None), "age_days": age,
                    "views": a["views"], "impressions": a["impressions"], "clicks": a["clicks"],
                    "orders": a["orders"], "gmv": a["gmv"],
                    "ctr": res.ctr.quantize(PCT) if res.ctr is not None else None,
                    "cvr": res.cvr.quantize(PCT) if res.cvr is not None else None,
                    "gpm": (a["gmv"] / a["views"] * 1000).quantize(Decimal(1)) if a["views"] else None,
                    "clicks_note": (f"measured product clicks on {a['clicks_measured_days']} days, derived "
                                    f"(views × CTR) on {a['clicks_derived_days']} days"),
                    "ad_spend": None, "net_profit": None, "ad_spend_note": NOT_AVAILABLE + ": Ads API",
                    "classification": res.classification.value, "confidence": res.confidence.value,
                    "reasons": list(res.reasons)})
    order = {Classification.WINNER: 0, Classification.PROMISING: 1, Classification.WATCH: 2,
             Classification.NEUTRAL: 3, Classification.LOW_ATTENTION: 4, Classification.TRAFFIC_NO_SALES: 5,
             Classification.FATIGUING: 6, Classification.LOSER: 7, Classification.INSUFFICIENT_DATA: 8}
    out.sort(key=lambda c: (order.get(Classification(c["classification"]), 9), -int(c["gmv"])))
    return out


# --- funnel & waterfall -------------------------------------------------------------------------
@dataclass
class FunnelCounts:
    """Video traffic funnel (views -> derived clicks -> video orders) + order pipeline
    (all orders -> completed -> settled). Product-card traffic has no impressions/clicks in the API."""
    impressions: int = 0
    clicks: int = 0
    video_orders: int = 0
    orders: int = 0
    completed: int = 0
    settled: int = 0

    def stages(self) -> list[FunnelStage]:
        return [FunnelStage("video_view", self.impressions), FunnelStage("video_click", self.clicks),
                FunnelStage("video_order", self.video_orders)]

    def pipeline(self) -> list[FunnelStage]:
        return [FunnelStage("order", self.orders), FunnelStage("completed", self.completed),
                FunnelStage("settled", self.settled)]


STAGE_NOTES = {"video_view": "video views (Shop API video analytics)",
               "video_click": "derived: views × click_through_rate (no click count in API)",
               "video_order": "orders attributed to videos by TikTok analytics",
               "order": "all orders with a profit row (incl. product-card traffic)",
               "completed": "COMPLETED/DELIVERED orders",
               "settled": "orders with a settled statement (lags 8–10 days; timing, not conversion)"}


def _steps(cs: list[FunnelStage], bs: list[FunnelStage]) -> list[dict[str, Any]]:
    steps = []
    for i in range(1, len(cs)):
        c_rate = ratio(cs[i].count, cs[i - 1].count)
        b_rate = ratio(bs[i].count, bs[i - 1].count)
        steps.append({"from": cs[i - 1].name, "to": cs[i].name, "count": cs[i].count,
                      "rate": c_rate, "baseline_rate": b_rate, "delta_pct": pct_change(c_rate, b_rate),
                      "timing_only": cs[i].name == "settled"})
    return steps


def funnel_view(cur: FunnelCounts, base: FunnelCounts, avg_profit_per_order: Decimal | None,
                min_stage_count: int = 30) -> dict[str, Any]:
    cs, bs = cur.stages(), base.stages()
    ps, pb = cur.pipeline(), base.pipeline()
    # deterioration: video funnel + order->completed; settled is a timing stage, never a conversion problem
    diag: FunnelDiagnosis | None = detect_funnel_deterioration(cs, bs, avg_profit_per_order, min_stage_count,
                                                               order_stage="video_order")
    if diag is None:
        diag = detect_funnel_deterioration(ps[:-1], pb[:-1], avg_profit_per_order, min_stage_count,
                                           order_stage="order")
    return {"stages": [{"name": s.name, "count": s.count, "note": STAGE_NOTES.get(s.name)} for s in cs],
            "steps": _steps(cs, bs),
            "pipeline": {"stages": [{"name": s.name, "count": s.count, "note": STAGE_NOTES.get(s.name)}
                                    for s in ps], "steps": _steps(ps, pb)},
            "coverage_note": "funnel covers video traffic only; product-card impressions/clicks are "
                             "NOT AVAILABLE in the Shop API",
            "diagnosis": None if diag is None else {
                "stage_from": diag.stage_from, "stage_to": diag.stage_to,
                "current_rate": diag.current_rate.quantize(PCT), "baseline_rate": diag.baseline_rate.quantize(PCT),
                "delta_pct": (diag.delta_pct / 100).quantize(PCT),
                "lost_orders": diag.lost_orders.quantize(Decimal(1)),
                "lost_profit": diag.lost_profit.quantize(Decimal(1)) if diag.lost_profit is not None else None,
                "evidence": list(diag.evidence), "estimated": True},
            "baseline_note": "baseline = previous comparable period"}


def waterfall(profits: Iterable[Any], advertising: dict | None = None) -> dict[str, Any]:
    """Σ current analytics_order_profit rows -> measured steps (statements) + COGS + blended ads."""
    s = {k: ZERO for k in ("sale_proceeds", "seller_discounts", "refunds", "platform_fees",
                           "affiliate_commission", "seller_shipping", "taxes", "subsidies", "adjustments",
                           "cogs", "packaging", "inbound_logistics", "other_variable", "contribution_profit",
                           "allocated_ad_cost", "estimated_net_profit", "net_seller_revenue")}
    from src.domain.dashboard.orders import inputs_known
    n = prov = cogs_missing = 0
    costs_known = ads_known = True
    for p in profits:
        costs_known = costs_known and inputs_known(p)
        ads_known = ads_known and bool((p.inputs_snapshot or {}).get("ad_cost_known"))
        n += 1
        prov += 1 if str(p.profit_status) == "PROVISIONAL" else 0
        cogs_missing += 1 if (getattr(p, "inputs_snapshot", None) or {}).get("cogs_missing") else 0
        for k in s:
            s[k] += _d(getattr(p, k, 0))
    ad_cost = advertising["cost"] if advertising is not None else (s["allocated_ad_cost"] if ads_known else None)
    net_profit = s["contribution_profit"] - ad_cost if costs_known and ad_cost is not None else None
    steps = [
        {"key": "revenue_after_seller_discounts", "amount": s["sale_proceeds"] - s["seller_discounts"],
         "measured": prov == 0},
        {"key": "refunds", "amount": -s["refunds"], "measured": prov == 0},
        {"key": "tiktok_fees", "amount": -(s["platform_fees"] + s["seller_shipping"]), "measured": prov == 0},
        {"key": "affiliate_commission", "amount": -s["affiliate_commission"], "measured": prov == 0},
        {"key": "taxes_adjustments_subsidies", "amount": s["subsidies"] + s["adjustments"] - s["taxes"],
         "measured": prov == 0},
        {"key": "net_seller_revenue", "amount": s["net_seller_revenue"], "subtotal": True, "measured": prov == 0},
        {"key": "cogs", "amount": -(s["cogs"] + s["packaging"] + s["inbound_logistics"] + s["other_variable"]),
         "measured": cogs_missing == 0 and costs_known, "note": f"{cogs_missing} orders on default/zero COGS" if cogs_missing else None},
        {"key": "contribution_before_ads", "amount": s["contribution_profit"], "subtotal": True,
         "measured": prov == 0},
        {"key": "ad_deductions_blended", "amount": -ad_cost if ad_cost is not None else None, "measured": False},
        {"key": "net_profit", "amount": net_profit, "subtotal": True, "measured": False},
    ]
    if not costs_known:
        for step in steps:
            if step["key"] not in ("revenue_after_seller_discounts", "ad_deductions_blended"):
                step["amount"], step["measured"] = None, False
    return {"orders": n, "provisional_orders": prov, "cogs_missing_orders": cogs_missing, "steps": steps,
            "note": "Measured = settled statements; provisional orders carry estimated fees; "
                    "ad cost = calendar Cost from the shop overview export, including days without orders; "
                    "GMV Pay is payment only. Taxes/credits not reconciled; profit remains an estimate."}


# --- data quality -------------------------------------------------------------------------------
def data_quality(freshness_minutes: int | None, cur: Totals, orders_missing_cogs: int,
                 unmapped_skus: int) -> DataQuality:
    cov = cur.settlement_coverage
    dq = compute_data_quality(DataQualityInputs(
        freshness_minutes=freshness_minutes, unmapped_skus=unmapped_skus,
        orders_missing_cogs=orders_missing_cogs, total_orders=cur.orders,
        settlement_coverage_pct=(cov * 100).quantize(RATIO) if cov is not None else None))
    if not cur.profit_known or cur.ad_cost_partial:
        reason = "Advertising or profit inputs missing" if not cur.profit_known else "Advertising export includes an incomplete day"
        return DataQuality(DQState.POOR if dq.state == DQState.POOR else DQState.PARTIAL,
                           min(dq.score, 70), (*dq.reasons, reason), dq.codes | {"PROFIT_INCOMPLETE"})
    return dq


@dataclass
class Overview:
    period: Period
    compare: Period
    cur: Totals
    prev: Totals
    health: dict[str, Any] = field(default_factory=dict)


# --- videos -> product cards (dependency) ---------------------------------------------------------
def pearson(xs: Sequence[Decimal], ys: Sequence[Decimal]) -> Decimal | None:
    n = len(xs)
    if n < 7 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return (sxy / (sxx.sqrt() * syy.sqrt())).quantize(PCT)


def lag_dependency(days: Sequence[dict[str, Any]], max_lag: int = 2) -> dict[str, Any]:
    """days: [{date, video_views, gmv_product_card}]; reindexed to a contiguous date range (missing days
    = 0) so that views(t) is aligned with card GMV(t+lag)."""
    if days:
        by = {d["date"]: d for d in days}
        lo, hi = min(by), max(by)
        days = [by.get(lo + timedelta(days=k), {"date": lo + timedelta(days=k), "video_views": 0,
                                                 "gmv_product_card": ZERO})
                for k in range((hi - lo).days + 1)]
    lags = []
    for lag in range(max_lag + 1):
        xs = [Decimal(d["video_views"]) for d in days[:len(days) - lag]] if lag else [Decimal(d["video_views"]) for d in days]
        ys = [_d(d["gmv_product_card"]) for d in days[lag:]]
        r = pearson(xs, ys)
        lags.append({"lag_days": lag, "correlation": r, "n": len(ys)})
    valid = [lg for lg in lags if lg["correlation"] is not None]
    best = max(valid, key=lambda lg: abs(lg["correlation"]))["lag_days"] if valid else None
    return {"lags": lags, "best_lag": best,
            "note": "Pearson correlation of daily video views vs product-card GMV shifted by lag; n = days; "
                    "|r|<0.3 weak, ≥0.5 strong; correlation ≠ causation"}


def video_product_map(vpm: Iterable[Any], product_rows_: Sequence[dict[str, Any]], product_meta: Mapping[int, Any],
                      video_meta: Mapping[int, Any], video_views: Mapping[int, int],
                      video_class: Mapping[int, str], period: Period) -> tuple[list[dict], list[dict]]:
    """video_product_metrics rows -> per-product (videos feeding it) and per-video (products it sells)."""
    pair: dict[tuple[int, int], dict[str, Any]] = {}
    for r in vpm:
        if not (period.start <= r.metric_date <= period.end):
            continue
        a = pair.setdefault((r.video_id, r.product_id), {"impressions": 0, "clicks": 0, "units_sold": 0,
                                                          "gmv": ZERO, "customers": 0})
        a["impressions"] += int(r.impressions or 0)
        a["clicks"] += int(r.clicks or 0)
        a["units_sold"] += int(r.units_sold or 0)
        a["customers"] += int(r.customers or 0)
        a["gmv"] += _d(r.gmv)
    prow = {p["product_id"]: p for p in product_rows_}
    by_product: dict[int, list[dict]] = {}
    by_video: dict[int, list[dict]] = {}
    for (vid, pid), a in pair.items():
        vm, pm = video_meta.get(vid), product_meta.get(pid)
        ctr = ratio(a["clicks"], a["impressions"]) if a["impressions"] else None
        by_product.setdefault(pid, []).append({"video_id": vid, "external_video_id": getattr(vm, "external_video_id", None),
                                               "caption": getattr(vm, "caption", None), **a, "ctr": ctr})
        by_video.setdefault(vid, []).append({"product_id": pid, "title": prow.get(pid, {}).get("title")
                                             or getattr(pm, "title", None) or f"product {pid}",
                                             **a, "ctr": ctr})
    products = []
    for pid in set(by_product) | set(prow):
        p, vids = prow.get(pid, {}), sorted(by_product.get(pid, []), key=lambda v: -v["gmv"])
        vg = sum((v["gmv"] for v in vids), ZERO)
        gmv = p.get("gmv", ZERO)
        meta = product_meta.get(pid)
        products.append({"product_id": pid, "title": p.get("title") or getattr(meta, "title", None) or f"product {pid}",
                         "external_product_id": p.get("external_product_id") or getattr(meta, "external_product_id", None),
                         "gmv": gmv, "orders": p.get("orders", 0), "net_profit": p.get("net_profit", ZERO),
                         "status": p.get("status", "NO_SALES"), "video_gmv": vg,
                         "video_units": sum(v["units_sold"] for v in vids),
                         "video_share": ratio(vg, gmv) if gmv > 0 else None,
                         "video_share_note": ("video GMV (TikTok video analytics) vs order-based product GMV; "
                                              "different day bucketing, can exceed 1"),
                         "video_impressions": sum(v["impressions"] for v in vids),
                         "video_clicks": sum(v["clicks"] for v in vids), "videos": vids})
    products.sort(key=lambda p: (-p["gmv"], -p["video_gmv"]))
    videos = [{"video_id": vid, "external_video_id": getattr(video_meta.get(vid), "external_video_id", None),
               "caption": getattr(video_meta.get(vid), "caption", None), "views": video_views.get(vid, 0),
               "classification": video_class.get(vid),
               "products": sorted(prods, key=lambda p: -p["gmv"])} for vid, prods in by_video.items()]
    videos.sort(key=lambda v: -sum(p["gmv"] for p in v["products"]))
    return products, videos


# --- history: how videos influenced products over time -----------------------------------------
LIFT_WINDOW = 7


def _lift_verdict(before_pd: Decimal, after_pd: Decimal, after_orders: int, min_orders: int) -> tuple[str, Decimal | None]:
    if after_orders + int(before_pd * LIFT_WINDOW) < min_orders:
        return "insufficient", None
    if before_pd == 0:
        return ("positive", None) if after_pd > 0 else ("neutral", None)
    lift = ((after_pd - before_pd) / before_pd).quantize(PCT)
    return ("positive" if lift >= Decimal("0.2") else "negative" if lift <= Decimal("-0.2") else "neutral"), lift


def video_history(vpm: Iterable[Any], product_daily_rows: Iterable[Any], video_daily: Mapping[int, Sequence[Any]],
                  video_meta: Mapping[int, Any], product_meta: Mapping[int, Any], period: Period,
                  min_orders: int, data_end: date | None = None, loaded_start: date | None = None,
                  tz: str | None = None) -> dict[str, Any]:
    """Per product: daily series (video vs total), video launch events, before/after lift per video.
    Per video: daily views→impressions→clicks→units, peak day, decay. Deterministic; lift = orders/day
    in the 7 days after publish vs 7 days before (all traffic, so it is an association, not attribution)."""
    vp_day: dict[tuple[int, date], dict[str, Any]] = {}
    vids_per_product: dict[int, set[int]] = {}
    for r in vpm:
        k = (r.product_id, r.metric_date)
        a = vp_day.setdefault(k, {"video_gmv": ZERO, "video_clicks": 0, "video_impressions": 0, "video_units": 0})
        a["video_gmv"] += _d(r.gmv)
        a["video_clicks"] += int(r.clicks or 0)
        a["video_impressions"] += int(r.impressions or 0)
        a["video_units"] += int(r.units_sold or 0)
        if int(r.impressions or 0) or _d(r.gmv):
            vids_per_product.setdefault(r.product_id, set()).add(r.video_id)
    pd_day: dict[tuple[int, date], Any] = {(r.product_id, r.metric_date): r for r in product_daily_rows}
    pids = {pid for pid, _ in pd_day} | {pid for pid, _ in vp_day}
    products = []
    for pid in sorted(pids):
        days = []
        for k in range(period.days):
            d = period.start + timedelta(days=k)
            p, v = pd_day.get((pid, d)), vp_day.get((pid, d), {})
            gmv = _d(getattr(p, "gmv", 0)) if p else ZERO
            vg = v.get("video_gmv", ZERO)
            days.append({"date": d, "gmv": gmv, "orders": int(getattr(p, "orders", 0) or 0) if p else 0,
                         "net_profit": _d(p.net_profit) if p and getattr(p, "ad_cost_known", False) and getattr(p, "profit_inputs_known", False) else None, "video_gmv": vg,
                         "non_video_gmv": max(gmv - vg, ZERO), "video_clicks": v.get("video_clicks", 0),
                         "video_impressions": v.get("video_impressions", 0), "video_units": v.get("video_units", 0)})
        events, lifts = [], []
        for vid in sorted(vids_per_product.get(pid, ())):
            vm = video_meta.get(vid)
            pday = _pub_date(vm, tz)
            if pday is None:
                continue
            ext = getattr(vm, "external_video_id", None)
            if period.start <= pday <= period.end:
                events.append({"date": pday, "video_id": vid, "external_video_id": ext, "type": "published"})
            before = [pd_day.get((pid, pday - timedelta(days=i))) for i in range(1, LIFT_WINDOW + 1)]
            after = [pd_day.get((pid, pday + timedelta(days=i))) for i in range(LIFT_WINDOW)]
            bo = sum(int(getattr(x, "orders", 0) or 0) for x in before if x)
            ao = sum(int(getattr(x, "orders", 0) or 0) for x in after if x)
            bg = sum((_d(getattr(x, "gmv", 0)) for x in before if x), ZERO)
            ag = sum((_d(getattr(x, "gmv", 0)) for x in after if x), ZERO)
            b_pd, a_pd = Decimal(bo) / LIFT_WINDOW, Decimal(ao) / LIFT_WINDOW
            verdict, lift = _lift_verdict(b_pd, a_pd, ao, min_orders)
            if data_end is not None and pday + timedelta(days=LIFT_WINDOW - 1) > data_end:
                verdict, lift = "pending", None  # after-window not complete yet
            elif loaded_start is not None and pday - timedelta(days=LIFT_WINDOW) < loaded_start:
                verdict, lift = "out_of_range", None  # before-window predates loaded data
            vg_after = sum((vp_day.get((pid, pday + timedelta(days=i)), {}).get("video_gmv", ZERO)
                            for i in range(LIFT_WINDOW)), ZERO)
            lifts.append({"video_id": vid, "external_video_id": ext, "published": pday,
                          "before": {"orders": bo, "gmv": bg, "orders_per_day": b_pd.quantize(RATIO)},
                          "after": {"orders": ao, "gmv": ag, "orders_per_day": a_pd.quantize(RATIO),
                                    "video_gmv": vg_after},
                          "lift_pct": lift, "verdict": verdict,
                          "note": "orders/day 7d after publish vs 7d before, all traffic (association)"})
        pm = product_meta.get(pid)
        products.append({"product_id": pid, "title": getattr(pm, "title", None) or f"product {pid}",
                         "days": days, "events": events, "lifts": lifts})
    videos = []
    for vid, rows in video_daily.items():
        by_day = {}
        for r in rows:
            if period.start <= r.metric_date <= period.end:
                by_day[r.metric_date] = {"date": r.metric_date, "views": int(r.views or 0),
                                         "impressions": int(r.impressions or 0), "clicks": int(r.product_clicks or 0),
                                         "orders": int(r.orders or 0), "gmv": _d(r.gmv)}
        if not by_day:
            continue
        series = [by_day[d] for d in sorted(by_day)]
        peak = max(series, key=lambda x: x["views"])
        last3 = series[-3:]
        decay = (sum(x["views"] for x in last3) / Decimal(len(last3)) / Decimal(peak["views"])).quantize(PCT) \
            if peak["views"] else None
        vm = video_meta.get(vid)
        videos.append({"video_id": vid, "external_video_id": getattr(vm, "external_video_id", None),
                       "caption": getattr(vm, "caption", None), "published_at": getattr(vm, "published_at", None),
                       "days": series, "peak_day": peak["date"], "peak_views": peak["views"],
                       "recent_vs_peak": decay,
                       "phase": "insufficient" if len(series) < 3 else "fading" if decay is not None and decay < Decimal("0.2")
                       else "steady" if decay is not None and decay < Decimal("0.7") else "rising"})
    videos.sort(key=lambda v: -sum(x["views"] for x in v["days"]))
    return {"products": products, "videos": videos,
            "notes": [("lift compares 7 days after a video's publish date with 7 days before on ALL traffic — "
                      "an association, not causal attribution"), "phase: rising/steady/fading = last-3-day views vs peak"]}
