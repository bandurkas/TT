from decimal import Decimal

from src.analytics import attribution, common, creative_scoring, data_quality
from src.analytics.creative_scoring import Confidence
from src.analytics.data_quality import (
    DataQualityInputs,
    DQState,
    apply_confidence_cap,
    compute_data_quality,
    confidence_cap,
)


def test_ok():
    dq = compute_data_quality(DataQualityInputs(freshness_minutes=30, total_orders=100,
                                                settlement_coverage_pct=Decimal(99)))
    assert dq.state == DQState.OK and dq.score == 100 and dq.reasons == ()
    assert confidence_cap(dq) == Confidence.HIGH


def test_partial_settlement_coverage():
    dq = compute_data_quality(DataQualityInputs(freshness_minutes=30, total_orders=100,
                                                settlement_coverage_pct=Decimal(82)))
    assert dq.state == DQState.PARTIAL
    assert "MISSING_SETTLEMENT" in dq.codes
    assert any("18.0% of orders lack final settlement" in r for r in dq.reasons)
    assert apply_confidence_cap(Confidence.HIGH, dq) == Confidence.MEDIUM
    assert apply_confidence_cap(Confidence.LOW, dq) == Confidence.LOW


def test_stale_forces_poor():
    dq = compute_data_quality(DataQualityInputs(freshness_minutes=500))
    assert dq.state == DQState.POOR and "STALE" in dq.codes
    assert confidence_cap(dq) == Confidence.LOW
    assert compute_data_quality(DataQualityInputs()).state == DQState.POOR


def test_missing_cogs_and_negatives_accumulate():
    dq = compute_data_quality(DataQualityInputs(freshness_minutes=10, orders_missing_cogs=40,
                                                total_orders=100, negative_values=2,
                                                duplicate_transactions=1, unmapped_skus=2))
    assert dq.state == DQState.POOR
    assert {"MISSING_COGS", "NEGATIVE_VALUES", "DUPLICATES", "UNMAPPED_SKU"} <= dq.codes
    assert 0 <= dq.score <= 100


def test_delayed_is_partial():
    dq = compute_data_quality(DataQualityInputs(freshness_minutes=200, missing_hours=1))
    assert dq.state == DQState.PARTIAL and dq.score == 80


def test_single_confidence_enum_shared():
    assert attribution.Confidence is common.Confidence
    assert creative_scoring.Confidence is common.Confidence
    assert data_quality.Confidence is common.Confidence
