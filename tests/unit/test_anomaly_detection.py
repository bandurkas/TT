from decimal import Decimal

from src.analytics.anomaly_detection import (
    AnomalyConfig,
    FunnelStage,
    Severity,
    detect_anomalies,
    detect_anomaly,
    detect_funnel_deterioration,
)

CFG = AnomalyConfig(min_samples={"ctr": 500})


def test_unfavorable_warning_and_critical():
    a = detect_anomaly("shop", "s", "orders", Decimal(70), Decimal(100), CFG)
    assert a is not None and a.severity == Severity.WARNING and a.delta_pct == Decimal("-30.0")
    a = detect_anomaly("shop", "s", "ad_spend", Decimal(200), Decimal(100), CFG)
    assert a is not None and a.severity == Severity.CRITICAL
    assert "ad_spend: 200 vs baseline 100 (+100.0%)" in a.evidence[0]


def test_favorable_opportunity_and_noise_filtered():
    a = detect_anomaly("video", "v", "orders", Decimal(130), Decimal(100), CFG)
    assert a is not None and a.severity == Severity.OPPORTUNITY
    assert detect_anomaly("video", "v", "orders", Decimal(110), Decimal(100), CFG) is None
    assert detect_anomaly("video", "v", "cpm", Decimal(50), Decimal(100), CFG).severity == (
        Severity.OPPORTUNITY
    )


def test_zero_baseline_safe():
    assert detect_anomaly("v", "1", "orders", Decimal(0), Decimal(0), CFG) is None
    assert detect_anomaly("v", "1", "orders", Decimal(5), None, CFG) is None
    a = detect_anomaly("v", "1", "ad_spend", Decimal(5), Decimal(0), CFG)
    assert a is not None and a.severity == Severity.INFO and a.delta_pct is None


def test_min_sample_guard():
    assert detect_anomaly("v", "1", "ctr", Decimal("0.01"), Decimal("0.02"), CFG, sample=100) is None
    assert detect_anomaly("v", "1", "ctr", Decimal("0.01"), Decimal("0.02"), CFG) is None
    a = detect_anomaly("v", "1", "ctr", Decimal("0.01"), Decimal("0.02"), CFG, sample=600)
    assert a is not None and a.severity == Severity.CRITICAL


def test_detect_anomalies_batch():
    out = detect_anomalies("shop", "s", {"orders": Decimal(50), "gmv": Decimal(100)},
                           {"orders": Decimal(100), "gmv": Decimal(100)}, CFG)
    assert [a.metric for a in out] == ["orders"]


def _funnel(imp, click, cart, order):
    return [FunnelStage("impression", imp), FunnelStage("click", click),
            FunnelStage("add_to_cart", cart), FunnelStage("order", order)]


def test_funnel_finds_worst_stage_and_lost_profit():
    cur = _funnel(10000, 300, 60, 30)
    base = _funnel(10000, 300, 120, 60)
    d = detect_funnel_deterioration(cur, base, avg_profit_per_order=Decimal(25))
    assert d is not None
    assert (d.stage_from, d.stage_to) == ("click", "add_to_cart")
    assert d.delta_pct == Decimal("-50.0")
    assert d.lost_at_stage == Decimal("60.0")
    assert d.lost_orders == Decimal("30.0")
    assert d.lost_profit == Decimal("750.00")
    assert any("lost profit" in e for e in d.evidence)


def test_funnel_no_deterioration_or_small_sample():
    assert detect_funnel_deterioration(_funnel(100, 10, 5, 2), _funnel(100, 10, 5, 2)) is None
    assert detect_funnel_deterioration(_funnel(20, 5, 1, 0), _funnel(20, 5, 4, 2)) is None
    assert detect_funnel_deterioration(_funnel(0, 0, 0, 0), _funnel(0, 0, 0, 0)) is None
    assert detect_funnel_deterioration(_funnel(1, 1, 1, 1)[:2], _funnel(1, 1, 1, 1)) is None
