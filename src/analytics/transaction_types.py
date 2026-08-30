"""Finance transaction taxonomy: native -> normalized mapping, sign rules, money conventions."""

from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum


class CurrencyMismatchError(ValueError):
    pass


_ZERO_DECIMAL_CURRENCIES = frozenset({"IDR", "JPY", "KRW", "VND", "CLP", "ISK", "HUF"})


def quantum(currency: str) -> Decimal:
    """Smallest representable unit for the currency (IDR -> 1, USD -> 0.01)."""
    return Decimal(1) if currency.upper() in _ZERO_DECIMAL_CURRENCIES else Decimal("0.01")


def require_same_currency(expected: str, actual: str, what: str) -> None:
    if expected != actual:
        raise CurrencyMismatchError(f"{what}: expected {expected}, got {actual}")


class NormalizedType(StrEnum):
    SALE_PROCEEDS = "SALE_PROCEEDS"
    PLATFORM_COMMISSION = "PLATFORM_COMMISSION"
    AFFILIATE_COMMISSION = "AFFILIATE_COMMISSION"
    SHIPPING_FEE = "SHIPPING_FEE"
    SHIPPING_ADJUSTMENT = "SHIPPING_ADJUSTMENT"
    TAX = "TAX"
    REFUND = "REFUND"
    REFUND_FEE_ADJUSTMENT = "REFUND_FEE_ADJUSTMENT"
    SELLER_DISCOUNT = "SELLER_DISCOUNT"
    PLATFORM_SUBSIDY = "PLATFORM_SUBSIDY"
    SERVICE_FEE = "SERVICE_FEE"
    TRANSACTION_FEE = "TRANSACTION_FEE"
    OTHER_ADJUSTMENT = "OTHER_ADJUSTMENT"
    UNKNOWN = "UNKNOWN"


class SignRule(StrEnum):
    INCREASES = "INCREASES"  # abs(amount) added to net seller revenue
    REDUCES = "REDUCES"  # abs(amount) subtracted
    SIGNED = "SIGNED"  # amount applied as-is (may be negative)
    EXCLUDED = "EXCLUDED"  # not part of revenue; reported separately


SIGN_RULES: dict[NormalizedType, SignRule] = {
    NormalizedType.SALE_PROCEEDS: SignRule.INCREASES,
    NormalizedType.PLATFORM_SUBSIDY: SignRule.INCREASES,
    NormalizedType.PLATFORM_COMMISSION: SignRule.REDUCES,
    NormalizedType.AFFILIATE_COMMISSION: SignRule.REDUCES,
    NormalizedType.SHIPPING_FEE: SignRule.REDUCES,
    NormalizedType.TAX: SignRule.REDUCES,
    NormalizedType.REFUND: SignRule.REDUCES,
    NormalizedType.SELLER_DISCOUNT: SignRule.REDUCES,
    NormalizedType.SERVICE_FEE: SignRule.REDUCES,
    NormalizedType.TRANSACTION_FEE: SignRule.REDUCES,
    NormalizedType.SHIPPING_ADJUSTMENT: SignRule.SIGNED,
    NormalizedType.REFUND_FEE_ADJUSTMENT: SignRule.SIGNED,
    NormalizedType.OTHER_ADJUSTMENT: SignRule.SIGNED,
    NormalizedType.UNKNOWN: SignRule.EXCLUDED,
}

ADJUSTMENT_TYPES = frozenset(
    {
        NormalizedType.SHIPPING_ADJUSTMENT,
        NormalizedType.REFUND_FEE_ADJUSTMENT,
        NormalizedType.OTHER_ADJUSTMENT,
    }
)

_PLATFORM_FEE_TYPES = frozenset(
    {
        NormalizedType.PLATFORM_COMMISSION,
        NormalizedType.SERVICE_FEE,
        NormalizedType.TRANSACTION_FEE,
    }
)


def is_platform_fee(t: NormalizedType) -> bool:
    return t in _PLATFORM_FEE_TYPES


def revenue_effect(t: NormalizedType, amount: Decimal) -> Decimal:
    """Signed contribution of one transaction to net seller revenue."""
    rule = SIGN_RULES[t]
    if rule is SignRule.INCREASES:
        return abs(amount)
    if rule is SignRule.REDUCES:
        return -abs(amount)
    if rule is SignRule.SIGNED:
        return amount
    return Decimal(0)


# Keys are canonicalized native names. Native names are UNVERIFIED against live API payloads;
# anything not listed stays UNKNOWN and keeps its native string.
NATIVE_TO_NORMALIZED: dict[str, NormalizedType] = {
    "sale": NormalizedType.SALE_PROCEEDS,
    "sales": NormalizedType.SALE_PROCEEDS,
    "sale_proceeds": NormalizedType.SALE_PROCEEDS,
    "sales_revenue": NormalizedType.SALE_PROCEEDS,
    "order_revenue": NormalizedType.SALE_PROCEEDS,
    "subtotal_after_seller_discounts": NormalizedType.SALE_PROCEEDS,
    "platform_commission": NormalizedType.PLATFORM_COMMISSION,
    "commission": NormalizedType.PLATFORM_COMMISSION,
    "commission_fee": NormalizedType.PLATFORM_COMMISSION,
    "referral_fee": NormalizedType.PLATFORM_COMMISSION,
    "affiliate_commission": NormalizedType.AFFILIATE_COMMISSION,
    "affiliate_commission_fee": NormalizedType.AFFILIATE_COMMISSION,
    "affiliate_partner_commission": NormalizedType.AFFILIATE_COMMISSION,
    "creator_commission": NormalizedType.AFFILIATE_COMMISSION,
    "shipping_fee": NormalizedType.SHIPPING_FEE,
    "actual_shipping_fee": NormalizedType.SHIPPING_FEE,
    "shipping_fee_seller": NormalizedType.SHIPPING_FEE,
    "shipping_adjustment": NormalizedType.SHIPPING_ADJUSTMENT,
    "shipping_fee_adjustment": NormalizedType.SHIPPING_ADJUSTMENT,
    "tax": NormalizedType.TAX,
    "vat": NormalizedType.TAX,
    "sales_tax": NormalizedType.TAX,
    "refund": NormalizedType.REFUND,
    "refund_amount": NormalizedType.REFUND,
    "return_refund": NormalizedType.REFUND,
    "refund_fee_adjustment": NormalizedType.REFUND_FEE_ADJUSTMENT,
    "refund_commission_reversal": NormalizedType.REFUND_FEE_ADJUSTMENT,
    "seller_discount": NormalizedType.SELLER_DISCOUNT,
    "seller_coupon": NormalizedType.SELLER_DISCOUNT,
    "seller_promotion": NormalizedType.SELLER_DISCOUNT,
    "platform_subsidy": NormalizedType.PLATFORM_SUBSIDY,
    "platform_discount": NormalizedType.PLATFORM_SUBSIDY,
    "platform_coupon": NormalizedType.PLATFORM_SUBSIDY,
    "shipping_fee_subsidy": NormalizedType.PLATFORM_SUBSIDY,
    "platform_shipping_subsidy": NormalizedType.PLATFORM_SUBSIDY,
    "service_fee": NormalizedType.SERVICE_FEE,
    "platform_service_fee": NormalizedType.SERVICE_FEE,
    "transaction_fee": NormalizedType.TRANSACTION_FEE,
    "payment_fee": NormalizedType.TRANSACTION_FEE,
    "payment_processing_fee": NormalizedType.TRANSACTION_FEE,
    "adjustment": NormalizedType.OTHER_ADJUSTMENT,
    "other_adjustment": NormalizedType.OTHER_ADJUSTMENT,
    "settlement_adjustment": NormalizedType.OTHER_ADJUSTMENT,
    "compensation": NormalizedType.OTHER_ADJUSTMENT,
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def canonical(native_type: object) -> str:
    if not isinstance(native_type, str):
        return ""
    return _NON_ALNUM.sub("_", native_type.strip().lower()).strip("_")


def normalize(native_type: object) -> NormalizedType:
    """Map a native TikTok transaction type to NormalizedType. Never raises; unmapped -> UNKNOWN."""
    return NATIVE_TO_NORMALIZED.get(canonical(native_type), NormalizedType.UNKNOWN)
