from datetime import date, timedelta
from decimal import Decimal

from src.analytics.creative_scoring import (
    Classification,
    Confidence,
    DailyMetrics,
    ScoringBaselines,
    ScoringConfig,
    VideoMetrics,
    classify_video,
    median,
)

CFG = ScoringConfig(minimum_sample_impressions=1000, minimum_sample_clicks=30,
                    minimum_sample_orders=5, minimum_net_margin=Decimal("0.10"))
BASE = ScoringBaselines(account_median_ctr=Decimal("0.02"), account_median_cvr=Decimal("0.05"))


def _vm(**kw) -> VideoMetrics:
    d = {"video_id": "v1", "impressions": 10000, "clicks": 200, "orders": 10,
         "gmv": Decimal(1000), "ad_spend": Decimal(100), "net_profit": Decimal(200)}
    d.update(kw)
    return VideoMetrics(**d)


def test_winner():
    r = classify_video(_vm(clicks=300, orders=20), BASE, CFG)
    assert r.classification == Classification.WINNER
    assert r.confidence == Confidence.HIGH
    assert any("CTR 3.00% vs account median 2.00% (50.0%)" in s for s in r.reasons)
    assert any("net margin" in s for s in r.reasons)


def test_product_median_preferred_over_account():
    base = ScoringBaselines(account_median_ctr=Decimal("0.02"), product_median_ctr=Decimal("0.04"))
    r = classify_video(_vm(clicks=300, orders=20), base, CFG)
    assert r.classification != Classification.WINNER
    assert any("product median" in s for s in r.reasons)


def test_insufficient_impressions():
    r = classify_video(_vm(impressions=500, clicks=20, orders=1), BASE, CFG)
    assert r.classification == Classification.INSUFFICIENT_DATA
    assert r.confidence == Confidence.LOW


def test_no_median_is_insufficient():
    r = classify_video(_vm(), ScoringBaselines(), CFG)
    assert r.classification == Classification.INSUFFICIENT_DATA


def test_promising_small_sample_strong_ctr():
    r = classify_video(_vm(impressions=1000, clicks=25, orders=1, net_profit=Decimal(5)), BASE, CFG)
    assert r.classification == Classification.PROMISING
    assert r.confidence == Confidence.LOW


def test_traffic_no_sales():
    r = classify_video(_vm(clicks=300, orders=0, gmv=Decimal(0), ad_spend=Decimal(0),
                           net_profit=Decimal(0)), BASE, CFG)
    assert r.classification == Classification.TRAFFIC_NO_SALES


def test_low_attention():
    r = classify_video(_vm(clicks=100, orders=6, net_profit=Decimal(50)), BASE, CFG)
    assert r.classification == Classification.LOW_ATTENTION


def test_loser_with_daily_saving():
    m = _vm(impressions=8200, clicks=65, orders=0, gmv=Decimal(0), ad_spend=Decimal(143000),
            net_profit=Decimal(-143000), age_days=2)
    r = classify_video(m, ScoringBaselines(account_median_ctr=Decimal("0.023"),
                                           account_median_cvr=Decimal("0.05")), CFG)
    assert r.classification == Classification.LOSER
    assert r.estimated_daily_saving == Decimal("71500.00")
    assert r.confidence == Confidence.HIGH
    assert any("saving" in s for s in r.reasons)


def _fatigue_daily(ctrs, cpms, cvrs):
    out = []
    for i, (ctr, cpm, cvr) in enumerate(zip(ctrs, cpms, cvrs, strict=True)):
        imp = 10000
        clicks = int(imp * ctr)
        out.append(DailyMetrics(date(2026, 8, 20) + timedelta(days=i), imp, clicks,
                                int(clicks * cvr), Decimal(imp) * Decimal(cpm)))
    return tuple(out)


def test_fatiguing_ctr_down_and_cpm_up():
    daily = _fatigue_daily([0.03, 0.025, 0.02], [0.01, 0.011, 0.013], [0.05, 0.05, 0.05])
    r = classify_video(_vm(daily=daily), BASE, CFG)
    assert r.classification == Classification.FATIGUING
    assert r.confidence == Confidence.MEDIUM
    assert any("CPM up" in s for s in r.reasons)


def test_ctr_down_without_cpm_or_cvr_change_is_not_fatigue():
    daily = _fatigue_daily([0.03, 0.025, 0.02], [0.01, 0.01, 0.01], [0.05, 0.05, 0.05])
    r = classify_video(_vm(daily=daily, clicks=300, orders=20), BASE, CFG)
    assert r.classification == Classification.WINNER


def test_neutral_average_video():
    r = classify_video(_vm(clicks=210, orders=10, net_profit=Decimal(50)), BASE, CFG)
    assert r.classification == Classification.NEUTRAL


def test_refund_rate_blocks_winner():
    r = classify_video(_vm(clicks=300, orders=20, refund_rate=Decimal("0.30")), BASE, CFG)
    assert r.classification == Classification.NEUTRAL
    assert any("refund rate" in s for s in r.reasons)


def test_median():
    assert median([]) is None
    assert median([Decimal(3), Decimal(1), Decimal(2)]) == Decimal(2)
    assert median([Decimal(1), Decimal(2)]) == Decimal("1.5")
