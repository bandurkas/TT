"""Pure dashboard computations over pre-aggregated rows (Decimal only). No DB, no LLM."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
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
from src.analytics.data_quality import DataQuality, DataQualityInputs, compute_data_quality

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
    days_with_data: int = 0

    @property
    def net_margin(self) -> Decimal | None:
        return ratio(self.net_profit, self.net_seller_revenue) if self.net_seller_revenue > 0 else None

    @property
    def blended_roas(self) -> Decimal | None:
        return ratio(self.net_seller_revenue, self.ad_cost, RATIO) if self.ad_cost > 0 else None

    @property
    def aov(self) -> Decimal | None:
        return (self.gmv / self.orders).quantize(Decimal(1)) if self.orders else None

    @property
    def cvr(self) -> Decimal | None:
        return ratio(self.orders, self.clicks) if self.clicks else None

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
        return ratio(self.contribution, self.net_seller_revenue) if self.net_seller_revenue > 0 else None

    @property
    def break_even_roas(self) -> Decimal | None:
        """Ad spend per net-revenue unit that leaves zero profit: 1 / contribution ratio."""
        c = self.contribution_ratio
        return (Decimal(1) / c).quantize(RATIO) if c and c > 0 else None


def sum_daily(rows: Iterable[Any], period: Period, funnel: Mapping[date, tuple[int, int]] | None = None,
              refunded: Mapping[date, int] | None = None) -> Totals:
    t = Totals()
    for r in rows:
        d = r.metric_date
        if not (period.start <= d <= period.end):
            continue
        t.days_with_data += 1
        for f in DAILY_FIELDS:
            v = getattr(r, f, 0) or 0
            setattr(t, f, getattr(t, f) + (int(v) if isinstance(getattr(t, f), int) else _d(v)))
    for d in (funnel or {}):
        if period.start <= d <= period.end:
            imp, clk = funnel[d]  # type: ignore[index]
            t.impressions += imp
            t.clicks += clk
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
        provisional: bool = False) -> dict[str, Any]:
    v = _d(value) if value is not None else None
    p = _d(prev) if prev is not None else None
    return {"key": key, "kind": kind, "value": v, "prev": p,
            "change_abs": (v - p) if v is not None and p is not None else None,
            "change_pct": pct_change(v, p), "sparkline": list(spark), "status": status,
            "note": note, "provisional": provisional}


def sparkline(rows: Iterable[Any], end: date, field_: str, n: int = 7) -> list[Decimal]:
    by = {r.metric_date: _d(getattr(r, field_, 0) or 0) for r in rows}
    return [by.get(end - timedelta(days=k), ZERO) for k in range(n - 1, -1, -1)]


def business_health(cur: Totals, prev: Totals, daily_rows: Sequence[Any], period: Period,
                    floor_margin: Decimal, dq: DataQuality) -> dict[str, Any]:
    prov = cur.provisional_orders > 0
    m, pm = cur.net_margin, prev.net_margin
    cards = [
        kpi("net_profit", cur.net_profit, prev.net_profit, sparkline(daily_rows, period.end, "net_profit"),
            status=_status(cur.net_profit, "up"), provisional=prov,
            note="accrual; ad cost BLENDED estimate" if cur.ad_cost else "accrual"),
        kpi("gmv", cur.gmv, prev.gmv, sparkline(daily_rows, period.end, "gmv"),
            status=_status(pct_change(cur.gmv, prev.gmv), "up"), note=f"{cur.units} units"),
        kpi("net_seller_revenue", cur.net_seller_revenue, prev.net_seller_revenue,
            sparkline(daily_rows, period.end, "net_seller_revenue"),
            status=_status(pct_change(cur.net_seller_revenue, prev.net_seller_revenue), "up"),
            note="after fees & refunds", provisional=prov),
        kpi("orders", cur.orders, prev.orders, sparkline(daily_rows, period.end, "orders"), kind="count",
            status=_status(pct_change(Decimal(cur.orders), Decimal(prev.orders)), "up"),
            note=f"{cur.refunded_orders} refunded"),
        kpi("ad_spend", cur.ad_cost, prev.ad_cost, sparkline(daily_rows, period.end, "ad_cost"),
            status=NEUTRAL, provisional=True,
            note=(f"{ratio(cur.ad_cost, cur.net_seller_revenue)!s} of net revenue"
                  if cur.net_seller_revenue > 0 else "GMV Max payout deductions")),
        kpi("net_margin", m, pm, [], kind="pct", status=_status(m, "up", floor_margin),
            note=f"floor {floor_margin}", provisional=prov),
        kpi("reported_roas", None, None, [], kind="ratio", status=NEUTRAL, note=NOT_AVAILABLE + ": Ads API"),
        kpi("blended_roas", cur.blended_roas, prev.blended_roas, [], kind="ratio",
            status=_status(cur.blended_roas, "up", cur.break_even_roas) if cur.break_even_roas else NEUTRAL,
            note=f"break-even {cur.break_even_roas}" if cur.break_even_roas else "net revenue / ad spend",
            provisional=True),
        kpi("aov", cur.aov, prev.aov, [], status=_status(pct_change(cur.aov, prev.aov), "up")),
        kpi("cvr", cur.cvr, prev.cvr, [], kind="pct", status=_status(pct_change(cur.cvr, prev.cvr), "up"),
            note="orders / product clicks"),
        kpi("refund_rate", cur.refund_rate, prev.refund_rate, [], kind="pct",
            status=_status(cur.refund_rate, "down", Decimal("0.10")), note="refunded orders / orders"),
        kpi("settlement_coverage", cur.settlement_coverage, prev.settlement_coverage, [], kind="pct",
            status=_status(cur.settlement_coverage, "up", Decimal("0.90")),
            note=f"{cur.provisional_orders} provisional"),
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
    score = round(sum(known) / len(known)) if known else 0
    grade = "GOOD" if score >= 75 else "FAIR" if score >= 50 else "POOR"
    return {"score": score, "grade": grade, "components": comp}


def unit_economics(t: Totals) -> dict[str, Any] | None:
    if not t.units:
        return None
    u = Decimal(t.units)
    q = lambda v: (v / u).quantize(Decimal(1))
    rev = q(t.gmv - t.refunds)
    fees = q(t.fees + t.affiliate)
    cogs = q(t.cogs)
    ads = q(t.ad_cost)
    return {"units": t.units, "revenue_per_unit": rev, "fees_per_unit": fees, "cogs_per_unit": cogs,
            "contribution_per_unit": q(t.contribution), "ad_cost_per_unit": ads,
            "net_per_unit": q(t.net_profit), "ad_cost_is_estimate": True}


# --- trends -------------------------------------------------------------------------------------
def trend_series(rows: Iterable[Any], period: Period) -> list[dict[str, Any]]:
    by = {r.metric_date: r for r in rows if period.start <= r.metric_date <= period.end}
    out, cum = [], ZERO
    for k in range(period.days):
        d = period.start + timedelta(days=k)
        r = by.get(d)
        np_ = _d(getattr(r, "net_profit", 0)) if r else ZERO
        cum += np_
        out.append({"date": d, "gmv": _d(getattr(r, "gmv", 0)) if r else ZERO,
                    "net_seller_revenue": _d(getattr(r, "net_seller_revenue", 0)) if r else ZERO,
                    "ad_cost": _d(getattr(r, "ad_cost", 0)) if r else ZERO, "net_profit": np_,
                    "cum_net_profit": cum, "orders": int(getattr(r, "orders", 0) or 0) if r else 0,
                    "settled_orders": int(getattr(r, "settled_orders", 0) or 0) if r else 0,
                    "provisional_orders": int(getattr(r, "provisional_orders", 0) or 0) if r else 0})
    return out


# --- products -------------------------------------------------------------------------------------
PRODUCT_STATUS = {"SCALE": "SCALE", "HEALTHY": "HEALTHY", "WATCH": "WATCH", "INVESTIGATE": "INVESTIGATE",
                  "REDUCE": "REDUCE", "SMALL_SAMPLE": "SMALL_SAMPLE"}


def product_status(t: Totals, floor: Decimal, min_orders: int) -> tuple[str, str]:
    if t.orders < min_orders:
        return "SMALL_SAMPLE", f"{t.orders} orders < {min_orders}"
    m = t.net_margin
    if m is None:
        return "SMALL_SAMPLE", "no net revenue"
    if t.net_profit < 0:
        return "REDUCE", f"net loss {t.net_profit}"
    if m < floor:
        return "INVESTIGATE", f"margin {m} below floor {floor}"
    if m >= 2 * floor and (t.cvr or ZERO) > 0:
        return "SCALE", f"margin {m} ≥ 2× floor"
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
                    "cogs": t.cogs, "ad_cost": t.ad_cost, "ad_cost_is_estimate": True,
                    "refunds": t.refunds, "net_profit": t.net_profit, "net_margin": t.net_margin,
                    "cvr": t.cvr, "ctr": t.ctr, "status": st, "status_reason": why})
    out.sort(key=lambda r: r["net_profit"], reverse=True)
    return out


# --- videos -------------------------------------------------------------------------------------
def video_cards(video_daily: Mapping[int, Sequence[Any]], video_meta: Mapping[int, Any], period: Period,
                today: date, cfg: ScoringConfig) -> list[dict[str, Any]]:
    """video_metrics rows grouped by video -> classified cards (creative_scoring). Ad spend per video
    is NOT AVAILABLE (Ads API) -> classification uses traffic/orders only; net_profit unknown -> 0."""
    agg: dict[int, dict[str, Any]] = {}
    for vid, rows in video_daily.items():
        imp = clk = orders = 0
        gmv = ZERO
        views = 0
        for r in rows:
            if not (period.start <= r.metric_date <= period.end):
                continue
            imp += int(r.impressions or 0)
            clk += int(r.product_clicks or 0)
            orders += int(r.orders or 0)
            views += int(r.views or 0)
            gmv += _d(r.gmv)
        if imp == clk == orders == views == 0:
            continue
        agg[vid] = {"impressions": imp, "clicks": clk, "orders": orders, "gmv": gmv, "views": views}
    ctrs = [ratio(a["clicks"], a["impressions"]) for a in agg.values() if a["impressions"]]
    cvrs = [ratio(a["orders"], a["clicks"]) for a in agg.values() if a["clicks"]]
    base = ScoringBaselines(account_median_ctr=median([c for c in ctrs if c is not None]),
                            account_median_cvr=median([c for c in cvrs if c is not None]))
    out = []
    for vid, a in agg.items():
        meta = video_meta.get(vid)
        pub = getattr(meta, "published_at", None)
        age = max(1, (today - pub.date()).days) if pub else 1
        res = classify_video(VideoMetrics(video_id=str(vid), impressions=a["impressions"], clicks=a["clicks"],
                                          orders=a["orders"], gmv=a["gmv"], age_days=age), base, cfg)
        out.append({"video_id": vid, "external_video_id": getattr(meta, "external_video_id", None),
                    "caption": getattr(meta, "caption", None), "published_at": pub,
                    "duration_seconds": getattr(meta, "duration_seconds", None), "age_days": age,
                    "views": a["views"], "impressions": a["impressions"], "clicks": a["clicks"],
                    "orders": a["orders"], "gmv": a["gmv"], "ctr": res.ctr, "cvr": res.cvr,
                    "gpm": (a["gmv"] / a["views"] * 1000).quantize(Decimal(1)) if a["views"] else None,
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
    impressions: int = 0
    clicks: int = 0
    orders: int = 0
    completed: int = 0
    settled: int = 0

    def stages(self) -> list[FunnelStage]:
        return [FunnelStage("impression", self.impressions), FunnelStage("click", self.clicks),
                FunnelStage("order", self.orders), FunnelStage("completed", self.completed),
                FunnelStage("settled", self.settled)]


def funnel_view(cur: FunnelCounts, base: FunnelCounts, avg_profit_per_order: Decimal | None,
                min_stage_count: int = 30) -> dict[str, Any]:
    cs, bs = cur.stages(), base.stages()
    steps = []
    for i in range(1, len(cs)):
        c_rate = ratio(cs[i].count, cs[i - 1].count)
        b_rate = ratio(bs[i].count, bs[i - 1].count)
        steps.append({"from": cs[i - 1].name, "to": cs[i].name, "count": cs[i].count,
                      "rate": c_rate, "baseline_rate": b_rate, "delta_pct": pct_change(c_rate, b_rate)})
    diag: FunnelDiagnosis | None = detect_funnel_deterioration(cs, bs, avg_profit_per_order, min_stage_count)
    return {"stages": [{"name": s.name, "count": s.count} for s in cs], "steps": steps,
            "diagnosis": None if diag is None else {
                "stage_from": diag.stage_from, "stage_to": diag.stage_to, "current_rate": diag.current_rate,
                "baseline_rate": diag.baseline_rate, "delta_pct": diag.delta_pct,
                "lost_orders": diag.lost_orders, "lost_profit": diag.lost_profit,
                "evidence": list(diag.evidence), "estimated": True},
            "baseline_note": "baseline = previous comparable period"}


def waterfall(profits: Iterable[Any]) -> dict[str, Any]:
    """Σ current analytics_order_profit rows -> measured steps (statements) + COGS + blended ads."""
    s = {k: ZERO for k in ("sale_proceeds", "seller_discounts", "refunds", "platform_fees",
                           "affiliate_commission", "seller_shipping", "taxes", "subsidies", "adjustments",
                           "cogs", "packaging", "inbound_logistics", "other_variable", "contribution_profit",
                           "allocated_ad_cost", "estimated_net_profit", "net_seller_revenue")}
    n = prov = 0
    for p in profits:
        n += 1
        prov += 1 if str(p.profit_status) == "PROVISIONAL" else 0
        for k in s:
            s[k] += _d(getattr(p, k, 0))
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
         "measured": True},
        {"key": "contribution_before_ads", "amount": s["contribution_profit"], "subtotal": True,
         "measured": prov == 0},
        {"key": "ad_deductions_blended", "amount": -s["allocated_ad_cost"], "measured": False},
        {"key": "net_profit", "amount": s["estimated_net_profit"], "subtotal": True, "measured": False},
    ]
    return {"orders": n, "provisional_orders": prov, "steps": steps,
            "note": "Measured = settled statements; provisional orders carry estimated fees; "
                    "ad cost = BLENDED payout deductions (estimate)."}


# --- data quality -------------------------------------------------------------------------------
def data_quality(freshness_minutes: int | None, cur: Totals, orders_missing_cogs: int,
                 unmapped_skus: int) -> DataQuality:
    cov = cur.settlement_coverage
    return compute_data_quality(DataQualityInputs(
        freshness_minutes=freshness_minutes, unmapped_skus=unmapped_skus,
        orders_missing_cogs=orders_missing_cogs, total_orders=cur.orders,
        settlement_coverage_pct=(cov * 100).quantize(RATIO) if cov is not None else None))


@dataclass
class Overview:
    period: Period
    compare: Period
    cur: Totals
    prev: Totals
    health: dict[str, Any] = field(default_factory=dict)
