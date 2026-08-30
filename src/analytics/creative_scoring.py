"""Deterministic creative classification with thresholds relative to medians (SPEC §9, §28)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from src.analytics.baselines import pct_change
from src.analytics.common import Confidence

ZERO = Decimal(0)


class Classification(StrEnum):
    WINNER = "WINNER"
    PROMISING = "PROMISING"
    TRAFFIC_NO_SALES = "TRAFFIC_NO_SALES"
    LOW_ATTENTION = "LOW_ATTENTION"
    LOSER = "LOSER"
    FATIGUING = "FATIGUING"
    NEUTRAL = "NEUTRAL"
    WATCH = "WATCH"  # profitable but refund rate above max: monitor, do not scale
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ScoringConfig:
    minimum_sample_impressions: int = 1000
    minimum_sample_clicks: int = 30
    minimum_sample_orders: int = 5
    minimum_net_margin: Decimal = Decimal("0.10")
    minimum_profit_per_order: Decimal = ZERO
    max_acceptable_cpa: Decimal | None = None
    winner_ctr_uplift: Decimal = Decimal("0.20")
    winner_cvr_uplift: Decimal = ZERO
    strong_ctr_uplift: Decimal = Decimal("0.20")
    low_ctr_ratio: Decimal = Decimal("0.70")
    low_cvr_ratio: Decimal = Decimal("0.50")
    max_refund_rate: Decimal = Decimal("0.15")  # absolute fallback
    refund_rate_median_factor: Decimal = Decimal(2)  # max = account median * factor when known
    fatigue_min_days: int = 3
    fatigue_ctr_drop: Decimal = Decimal("0.15")
    fatigue_cpm_rise: Decimal = Decimal("0.15")
    fatigue_cvr_drop: Decimal = Decimal("0.15")


@dataclass(frozen=True)
class DailyMetrics:
    day: date
    impressions: int
    clicks: int
    orders: int
    ad_spend: Decimal = ZERO


@dataclass(frozen=True)
class VideoMetrics:
    video_id: str
    impressions: int
    clicks: int
    orders: int
    gmv: Decimal = ZERO
    ad_spend: Decimal = ZERO
    net_profit: Decimal = ZERO
    refund_rate: Decimal | None = None
    age_days: int = 1
    daily: tuple[DailyMetrics, ...] = ()


@dataclass(frozen=True)
class ScoringBaselines:
    account_median_ctr: Decimal | None = None
    account_median_cvr: Decimal | None = None
    product_median_ctr: Decimal | None = None
    product_median_cvr: Decimal | None = None
    account_median_refund_rate: Decimal | None = None


@dataclass(frozen=True)
class ClassificationResult:
    video_id: str
    classification: Classification
    confidence: Confidence
    reasons: tuple[str, ...]
    ctr: Decimal | None
    cvr: Decimal | None
    ad_spend: Decimal
    net_profit: Decimal
    estimated_daily_saving: Decimal | None = None


@dataclass
class _Ctx:
    m: VideoMetrics
    cfg: ScoringConfig
    ctr: Decimal | None
    cvr: Decimal | None
    ctr_ref: Decimal | None
    cvr_ref: Decimal | None
    ctr_label: str
    cvr_label: str
    reasons: list[str] = field(default_factory=list)


def _ratio(num: int | Decimal, den: int | Decimal) -> Decimal | None:
    return None if den == 0 else Decimal(num) / Decimal(den)


def _pct(v: Decimal | None) -> str:
    return "n/a" if v is None else f"{(v * 100).quantize(Decimal('0.01'))}%"


def _rel(cur: Decimal | None, ref: Decimal | None) -> Decimal | None:
    return None if cur is None or ref is None or ref == 0 else cur / ref


def _pick(product: Decimal | None, account: Decimal | None) -> tuple[Decimal | None, str]:
    if product is not None:
        return product, "product median"
    return account, "account median"


def _confidence(m: VideoMetrics, cfg: ScoringConfig, zero_orders_high: bool = True) -> Confidence:
    """HIGH needs 2x click sample and 2x order sample; 0 orders count as HIGH only when
    `zero_orders_high` (no-sales verdicts), never for NEUTRAL."""
    if m.clicks >= 2 * cfg.minimum_sample_clicks and (
        (m.orders > 0 and m.orders >= 2 * cfg.minimum_sample_orders)
        or (m.orders == 0 and zero_orders_high)
    ):
        return Confidence.HIGH
    if m.clicks >= cfg.minimum_sample_clicks:
        return Confidence.MEDIUM
    return Confidence.LOW


def _downgrade(conf: Confidence) -> Confidence:
    return Confidence.MEDIUM if conf is Confidence.HIGH else Confidence.LOW


def _max_refund_rate(cfg: ScoringConfig, baselines: ScoringBaselines) -> Decimal:
    med = baselines.account_median_refund_rate
    return med * cfg.refund_rate_median_factor if med is not None else cfg.max_refund_rate


def _saving(m: VideoMetrics) -> Decimal:
    days = max(1, len(m.daily) or m.age_days)
    return (m.ad_spend / Decimal(days)).quantize(Decimal("0.01"))


def _fatigue(c: _Ctx) -> bool:
    days = [d for d in c.m.daily if d.impressions > 0]
    n = c.cfg.fatigue_min_days
    if len(days) < n or c.m.clicks < c.cfg.minimum_sample_clicks:
        return False
    days = sorted(days, key=lambda d: d.day)[-n:]
    ctrs = [Decimal(d.clicks) / Decimal(d.impressions) for d in days]
    if any(ctrs[i] <= ctrs[i + 1] for i in range(len(ctrs) - 1)):
        return False
    if ctrs[0] == 0 or (ctrs[0] - ctrs[-1]) / ctrs[0] < c.cfg.fatigue_ctr_drop:
        return False
    first, last = days[0], days[-1]
    cpm0, cpm1 = _ratio(first.ad_spend, first.impressions), _ratio(last.ad_spend, last.impressions)
    cvr0, cvr1 = _ratio(first.orders, first.clicks), _ratio(last.orders, last.clicks)
    cpm_up = cpm0 is not None and cpm1 is not None and cpm0 > 0 and (
        (cpm1 - cpm0) / cpm0 >= c.cfg.fatigue_cpm_rise
    )
    cvr_down = cvr0 is not None and cvr1 is not None and cvr0 > 0 and (
        (cvr0 - cvr1) / cvr0 >= c.cfg.fatigue_cvr_drop
    )
    if not (cpm_up or cvr_down):
        return False
    c.reasons.append(
        f"CTR fell {n} days in a row: {_pct(ctrs[0])} -> {_pct(ctrs[-1])} "
        f"({pct_change(ctrs[-1], ctrs[0])}%)"
    )
    if cpm_up:
        c.reasons.append(f"CPM up {pct_change(cpm1, cpm0)}% ({cpm0:.4f} -> {cpm1:.4f})")
    if cvr_down:
        c.reasons.append(f"CVR down: {_pct(cvr0)} -> {_pct(cvr1)}")
    return True


def _result(
    c: _Ctx, cls: Classification, conf: Confidence, saving: Decimal | None = None
) -> ClassificationResult:
    return ClassificationResult(
        video_id=c.m.video_id,
        classification=cls,
        confidence=conf,
        reasons=tuple(c.reasons),
        ctr=c.ctr,
        cvr=c.cvr,
        ad_spend=c.m.ad_spend,
        net_profit=c.m.net_profit,
        estimated_daily_saving=saving,
    )


def classify_video(
    metrics: VideoMetrics, baselines: ScoringBaselines, config: ScoringConfig
) -> ClassificationResult:
    """Order of verdicts: FATIGUING > INSUFFICIENT_DATA > (small clicks) > WINNER > LOSER >
    LOW_ATTENTION > TRAFFIC_NO_SALES > (small orders) > WATCH > NEUTRAL.

    LOSER: net_profit < 0 with spend and either weak CTR/CVR or enough orders to trust the loss.
    Refund rate above max (account median * factor, else absolute): LOSER if net_profit <= 0,
    otherwise WATCH with confidence downgraded one level; never WINNER or NEUTRAL.
    """
    m, cfg = metrics, config
    ctr_ref, ctr_label = _pick(baselines.product_median_ctr, baselines.account_median_ctr)
    cvr_ref, cvr_label = _pick(baselines.product_median_cvr, baselines.account_median_cvr)
    c = _Ctx(m, cfg, _ratio(m.clicks, m.impressions), _ratio(m.orders, m.clicks),
             ctr_ref, cvr_ref, ctr_label, cvr_label)
    c.reasons.append(
        f"{m.impressions} impressions, {m.clicks} clicks, {m.orders} orders, "
        f"spend {m.ad_spend}, net profit {m.net_profit}"
    )

    if _fatigue(c):
        conf = Confidence.HIGH if len(m.daily) >= cfg.fatigue_min_days + 2 else Confidence.MEDIUM
        return _result(c, Classification.FATIGUING, conf)

    if m.impressions < cfg.minimum_sample_impressions:
        c.reasons.append(f"impressions below minimum sample {cfg.minimum_sample_impressions}")
        return _result(c, Classification.INSUFFICIENT_DATA, Confidence.LOW)
    if ctr_ref is None:
        c.reasons.append("no CTR median available for relative comparison")
        return _result(c, Classification.INSUFFICIENT_DATA, Confidence.LOW)

    ctr_rel, cvr_rel = _rel(c.ctr, ctr_ref), _rel(c.cvr, cvr_ref)
    c.reasons.append(f"CTR {_pct(c.ctr)} vs {ctr_label} {_pct(ctr_ref)} "
                     f"({pct_change(c.ctr, ctr_ref)}%)")
    if cvr_ref is not None:
        c.reasons.append(f"CVR {_pct(c.cvr)} vs {cvr_label} {_pct(cvr_ref)} "
                         f"({pct_change(c.cvr, cvr_ref)}%)")
    ctr_strong = ctr_rel is not None and ctr_rel >= 1 + cfg.strong_ctr_uplift
    ctr_low = ctr_rel is not None and ctr_rel < cfg.low_ctr_ratio
    cvr_low = cvr_ref is not None and (c.cvr is None or c.cvr < cvr_ref * cfg.low_cvr_ratio)
    conf = _confidence(m, cfg)

    if m.clicks < cfg.minimum_sample_clicks:
        c.reasons.append(f"clicks below minimum sample {cfg.minimum_sample_clicks}")
        if ctr_low:
            return _result(c, Classification.LOW_ATTENTION, Confidence.MEDIUM)
        if ctr_strong:
            return _result(c, Classification.PROMISING, Confidence.LOW)
        return _result(c, Classification.INSUFFICIENT_DATA, Confidence.LOW)

    margin = _ratio(m.net_profit, m.gmv) if m.gmv > 0 else None  # margin on GMV
    max_refund = _max_refund_rate(cfg, baselines)
    refund_ok = m.refund_rate is None or m.refund_rate <= max_refund
    profit_per_order = _ratio(m.net_profit, m.orders)
    cpa = _ratio(m.ad_spend, m.orders)
    cpa_ok = cfg.max_acceptable_cpa is None or (cpa is not None and cpa <= cfg.max_acceptable_cpa)

    if (
        m.orders >= cfg.minimum_sample_orders
        and ctr_rel is not None and ctr_rel >= 1 + cfg.winner_ctr_uplift
        and (cvr_rel is None or cvr_rel >= 1 + cfg.winner_cvr_uplift)
        and m.net_profit > 0
        and margin is not None and margin >= cfg.minimum_net_margin
        and profit_per_order is not None and profit_per_order >= cfg.minimum_profit_per_order
        and refund_ok and cpa_ok
    ):
        c.reasons.append(
            f"net margin on GMV {_pct(margin)} >= floor {_pct(cfg.minimum_net_margin)}"
        )
        return _result(c, Classification.WINNER, conf)

    enough_orders = m.orders >= cfg.minimum_sample_orders
    if not refund_ok:
        c.reasons.append(f"refund rate {_pct(m.refund_rate)} above max {_pct(max_refund)}")
    if m.ad_spend > 0 and (
        (m.net_profit < 0 and (cvr_low or ctr_low or enough_orders))
        or (m.net_profit <= 0 and not refund_ok)
    ):
        saving = _saving(m)
        c.reasons.append(f"negative contribution after ads: {m.net_profit}")
        c.reasons.append(f"estimated saving ~{saving}/day if spend stops")
        return _result(c, Classification.LOSER, conf, saving)
    if not refund_ok and m.net_profit <= 0:
        c.reasons.append(f"non-positive contribution with high refunds: {m.net_profit}")
        return _result(c, Classification.LOSER, conf)
    if m.ad_spend == 0 and m.net_profit < 0:
        c.reasons.append(f"negative profit without ad spend: {m.net_profit}")
        return _result(c, Classification.WATCH, _downgrade(conf))

    if ctr_low:
        c.reasons.append("CTR significantly below median with enough impressions")
        return _result(c, Classification.LOW_ATTENTION, conf)

    if cvr_low and ctr_rel is not None and ctr_rel >= 1:
        c.reasons.append("traffic at/above median but conversion weak")
        return _result(c, Classification.TRAFFIC_NO_SALES, conf)

    if m.orders < cfg.minimum_sample_orders:
        c.reasons.append(f"orders below minimum sample {cfg.minimum_sample_orders}")
        if ctr_strong or (cvr_rel is not None and cvr_rel >= 1):
            return _result(c, Classification.PROMISING, Confidence.LOW)
        return _result(c, Classification.INSUFFICIENT_DATA, Confidence.LOW)

    if not refund_ok:
        c.reasons.append("profitable but refunds above max: monitor, do not scale")
        return _result(c, Classification.WATCH, _downgrade(conf))
    c.reasons.append("within normal range of medians")
    return _result(c, Classification.NEUTRAL, _confidence(m, cfg, zero_orders_high=False))


def median(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
