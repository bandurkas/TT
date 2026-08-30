from decimal import Decimal

import pytest

from src.analytics.attribution import (
    AllocationError,
    AttributionMethod,
    Confidence,
    ProportionalBasis,
    RoasKind,
    allocate_proportionally,
    blended,
    blended_ratio,
    direct_creative,
    platform_reported,
    proportional,
    roas,
)

D = Decimal


def test_allocate_reconciles_exactly_idr() -> None:
    out = allocate_proportionally(D(100), {"a": D(1), "b": D(1), "c": D(1)}, "IDR")
    assert sum(out.values()) == D(100)
    assert out == {"a": D(34), "b": D(33), "c": D(33)}


def test_allocate_remainder_goes_to_largest_weight() -> None:
    out = allocate_proportionally(D(10), {"small": D(1), "big": D(2)}, "IDR")
    assert out == {"small": D(3), "big": D(7)}


def test_allocate_tie_goes_to_first_key() -> None:
    out = allocate_proportionally(D(1), {"x": D(5), "y": D(5)}, "IDR")
    assert out == {"x": D(1), "y": D(0)}


def test_allocate_usd_precision() -> None:
    out = allocate_proportionally(D("10.00"), {"a": D(1), "b": D(1), "c": D(1)}, "USD")
    assert sum(out.values()) == D("10.00")
    assert out == {"a": D("3.34"), "b": D("3.33"), "c": D("3.33")}
    assert all(v == v.quantize(D("0.01")) for v in out.values())


def test_allocate_negative_total() -> None:
    out = allocate_proportionally(D(-10), {"a": D(1), "b": D(2)}, "IDR")
    assert out == {"a": D(-3), "b": D(-7)}
    assert sum(out.values()) == D(-10)


def test_allocate_zero_share_is_plain_zero_not_negative_zero() -> None:
    out = allocate_proportionally(D(-10), {"a": D(1), "b": D(0)}, "IDR")
    assert out == {"a": D(-10), "b": D(0)}
    assert not out["b"].is_signed() and str(out["b"]) == "0"


def test_allocate_zero_weights_equal_split() -> None:
    out = allocate_proportionally(D(7), {"a": D(0), "b": D(0)}, "IDR")
    assert out == {"a": D(4), "b": D(3)}


def test_allocate_empty_and_negative_weights() -> None:
    assert allocate_proportionally(D(0), {}, "IDR") == {}
    with pytest.raises(AllocationError):
        allocate_proportionally(D(5), {}, "IDR")
    with pytest.raises(AllocationError):
        allocate_proportionally(D(5), {"a": D(-1)}, "IDR")


def test_platform_reported_passthrough() -> None:
    r = platform_reported({"c1": D(12000), "c2": D(3000)}, "IDR", total_spend=D(16000))
    assert r.method is AttributionMethod.PLATFORM_REPORTED
    assert r.confidence is Confidence.HIGH
    assert r.allocated_total == D(15000)
    assert r.unallocated == D(1000)
    assert "not incremental" in r.note
    assert r.warnings == ()


def test_platform_reported_over_allocation_warns() -> None:
    r = platform_reported({"c1": D(12000)}, "IDR", total_spend=D(10000))
    assert r.unallocated == D(-2000)
    assert "reported_exceeds_total" in r.warnings


def test_direct_creative_splits_by_order_value() -> None:
    r = direct_creative(D(12000), {"o1": D(75000), "o2": D(25000)}, "IDR")
    assert r.method is AttributionMethod.DIRECT_CREATIVE
    assert r.confidence is Confidence.HIGH
    assert r.allocations == {"o1": D(9000), "o2": D(3000)}
    assert r.allocated_total == r.total


def test_direct_creative_without_orders_is_unallocated() -> None:
    r = direct_creative(D(5000), {}, "IDR")
    assert r.unallocated == D(5000)
    assert r.confidence is Confidence.LOW
    assert "no_linked_orders" in r.warnings


def test_proportional_gmv_medium_orders_low() -> None:
    g = proportional(D(1000), {"v1": D(300), "v2": D(700)}, "IDR")
    assert g.confidence is Confidence.MEDIUM
    assert g.allocations == {"v1": D(300), "v2": D(700)}
    o = proportional(D(1000), {"v1": D(1), "v2": D(2)}, "IDR", basis=ProportionalBasis.ORDERS)
    assert o.confidence is Confidence.LOW
    assert sum(o.allocations.values()) == D(1000)


def test_proportional_zero_weights_downgrades() -> None:
    r = proportional(D(9), {"a": D(0), "b": D(0), "c": D(0)}, "IDR")
    assert r.confidence is Confidence.LOW
    assert "zero_weights_equal_split" in r.warnings
    assert sum(r.allocations.values()) == D(9)


def test_proportional_no_weights() -> None:
    r = proportional(D(9), {}, "IDR")
    assert r.unallocated == D(9)


def test_blended_ratio() -> None:
    assert blended_ratio(D(12000), D(62000)) == D("0.193548")
    assert blended_ratio(D(100), D(0)) is None
    assert blended_ratio(D(100), D(-5)) is None


def test_blended_allocation_reconciles_and_is_low_confidence() -> None:
    r = blended(D(1000), {"o1": D(600), "o2": D(300), "o3": D(-100)}, "IDR")
    assert r.method is AttributionMethod.BLENDED
    assert r.confidence is Confidence.LOW
    assert r.allocations == {"o1": D(667), "o2": D(333), "o3": D(0)}
    assert r.allocated_total == D(1000)
    assert "ratio 1.250000 = 1000/800" in r.note  # SPEC §6.4-D: all net revenue, incl. negative


def test_blended_undefined_when_negative_orders_dominate() -> None:
    r = blended(D(1000), {"o1": D(100), "o2": D(-300)}, "IDR")
    assert r.unallocated == D(1000) and "undefined_ratio" in r.warnings
    assert r.allocations == {"o1": D(0), "o2": D(0)}


def test_blended_undefined_when_no_revenue() -> None:
    r = blended(D(1000), {"o1": D(0)}, "IDR")
    assert r.unallocated == D(1000)
    assert "undefined_ratio" in r.warnings


def test_roas_labels() -> None:
    r = roas(RoasKind.REPORTED, D(300000), D(100000))
    assert r.value == D("3.000000")
    assert r.label == "Reported ROAS"
    assert roas(RoasKind.BLENDED, D(1), D(0)).value is None
