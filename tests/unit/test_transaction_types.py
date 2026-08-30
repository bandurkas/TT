from decimal import Decimal

import pytest

from src.analytics.transaction_types import (
    ADJUSTMENT_TYPES,
    SIGN_RULES,
    CurrencyMismatchError,
    NormalizedType,
    SignRule,
    canonical,
    normalize,
    quantum,
    require_same_currency,
    revenue_effect,
)


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        ("SALE", NormalizedType.SALE_PROCEEDS),
        ("sales_revenue", NormalizedType.SALE_PROCEEDS),
        ("PLATFORM_COMMISSION", NormalizedType.PLATFORM_COMMISSION),
        ("Commission Fee", NormalizedType.PLATFORM_COMMISSION),
        ("affiliate_commission", NormalizedType.AFFILIATE_COMMISSION),
        ("shipping-fee", NormalizedType.SHIPPING_FEE),
        ("shipping_fee_adjustment", NormalizedType.SHIPPING_ADJUSTMENT),
        ("VAT", NormalizedType.TAX),
        ("refund", NormalizedType.REFUND),
        ("refund_fee_adjustment", NormalizedType.REFUND_FEE_ADJUSTMENT),
        ("seller_discount", NormalizedType.SELLER_DISCOUNT),
        ("platform_discount", NormalizedType.PLATFORM_SUBSIDY),
        ("service_fee", NormalizedType.SERVICE_FEE),
        ("transaction_fee", NormalizedType.TRANSACTION_FEE),
        ("settlement_adjustment", NormalizedType.OTHER_ADJUSTMENT),
    ],
)
def test_normalize_known(native: str, expected: NormalizedType) -> None:
    assert normalize(native) is expected


@pytest.mark.parametrize("native", ["", "   ", "MYSTERY_FEE_2027", None, 42, object()])
def test_normalize_unknown_never_raises(native: object) -> None:
    assert normalize(native) is NormalizedType.UNKNOWN


def test_canonical_strips_and_collapses() -> None:
    assert canonical("  Platform--Commission  ") == "platform_commission"
    assert canonical(None) == ""


def test_every_type_has_sign_rule() -> None:
    assert set(SIGN_RULES) == set(NormalizedType)
    assert SIGN_RULES[NormalizedType.UNKNOWN] is SignRule.EXCLUDED
    assert all(SIGN_RULES[t] is SignRule.SIGNED for t in ADJUSTMENT_TYPES)


def test_revenue_effect_sign_conventions() -> None:
    assert revenue_effect(NormalizedType.SALE_PROCEEDS, Decimal(75000)) == Decimal(75000)
    assert revenue_effect(NormalizedType.PLATFORM_COMMISSION, Decimal(8000)) == Decimal(-8000)
    assert revenue_effect(NormalizedType.PLATFORM_COMMISSION, Decimal(-8000)) == Decimal(-8000)
    assert revenue_effect(NormalizedType.PLATFORM_SUBSIDY, Decimal(-500)) == Decimal(500)
    assert revenue_effect(NormalizedType.OTHER_ADJUSTMENT, Decimal(-2000)) == Decimal(-2000)
    assert revenue_effect(NormalizedType.OTHER_ADJUSTMENT, Decimal(1000)) == Decimal(1000)
    assert revenue_effect(NormalizedType.UNKNOWN, Decimal(999)) == Decimal(0)


def test_quantum_per_currency() -> None:
    assert quantum("IDR") == Decimal(1)
    assert quantum("idr") == Decimal(1)
    assert quantum("USD") == Decimal("0.01")


def test_require_same_currency() -> None:
    require_same_currency("IDR", "IDR", "x")
    with pytest.raises(CurrencyMismatchError):
        require_same_currency("IDR", "USD", "x")
