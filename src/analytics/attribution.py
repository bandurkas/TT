"""Advertising cost attribution models (SPEC §6.4, §7). Pure Decimal, exact reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from src.analytics.common import Confidence
from src.analytics.transaction_types import quantum

ZERO = Decimal(0)
RATIO_PLACES = Decimal("0.000001")


class AttributionMethod(StrEnum):
    PLATFORM_REPORTED = "PLATFORM_REPORTED"
    DIRECT_CREATIVE = "DIRECT_CREATIVE"
    PROPORTIONAL = "PROPORTIONAL"
    BLENDED = "BLENDED"


class ProportionalBasis(StrEnum):
    GMV = "GMV"
    ORDERS = "ORDERS"


class RoasKind(StrEnum):
    REPORTED = "REPORTED"
    ATTRIBUTED = "ATTRIBUTED"
    ADJUSTED = "ADJUSTED"
    BLENDED = "BLENDED"


@dataclass(frozen=True)
class LabeledRoas:
    kind: RoasKind
    value: Decimal | None  # None when spend is zero

    @property
    def label(self) -> str:
        return f"{self.kind.value.capitalize()} ROAS"


@dataclass(frozen=True)
class AttributionResult:
    allocations: dict[str, Decimal]
    method: AttributionMethod
    confidence: Confidence
    currency: str
    total: Decimal
    unallocated: Decimal = ZERO
    note: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def allocated_total(self) -> Decimal:
        return sum(self.allocations.values(), ZERO)


class AllocationError(ValueError):
    pass


def allocate_proportionally(
    total: Decimal, weights: Mapping[str, Decimal], currency: str
) -> dict[str, Decimal]:
    """Split `total` by weights, quantized to the currency unit; sum(result) == total exactly.

    Each share is floored (ROUND_DOWN) to the quantum; the remainder goes to the largest
    weight (ties: first key in input order). Zero total weight with non-zero total -> equal split.
    Negative weights are rejected.
    """
    if not weights:
        if total != ZERO:
            raise AllocationError("cannot allocate non-zero total to empty weights")
        return {}
    if any(w < ZERO for w in weights.values()):
        raise AllocationError("negative weight")
    q = quantum(currency)
    keys = list(weights)
    weight_sum = sum(weights.values(), ZERO)
    if weight_sum == ZERO:
        eff = {k: Decimal(1) for k in keys}
        weight_sum = Decimal(len(keys))
    else:
        eff = dict(weights)
    sign = Decimal(-1) if total < ZERO else Decimal(1)
    magnitude = abs(total)
    shares = {k: (magnitude * eff[k] / weight_sum).quantize(q, rounding=ROUND_DOWN) for k in keys}
    remainder = magnitude - sum(shares.values(), ZERO)
    if remainder != ZERO:
        largest = max(keys, key=lambda k: (eff[k], -keys.index(k)))
        shares[largest] += remainder
    return {k: sign * v if v else ZERO for k, v in shares.items()}  # no Decimal('-0')


def platform_reported(
    reported: Mapping[str, Decimal], currency: str, total_spend: Decimal | None = None
) -> AttributionResult:
    """Model A: pass through TikTok-reported per-entity spend. Exact as reported, not causal."""
    allocations = dict(reported)
    allocated = sum(allocations.values(), ZERO)
    total = allocated if total_spend is None else total_spend
    unallocated = total - allocated
    warnings = ("reported_exceeds_total",) if unallocated < ZERO else ()
    return AttributionResult(
        allocations=allocations,
        method=AttributionMethod.PLATFORM_REPORTED,
        confidence=Confidence.HIGH,
        currency=currency,
        total=total,
        unallocated=unallocated,
        note="TikTok-reported attribution; reported, not incremental",
        warnings=warnings,
    )


def direct_creative(
    spend: Decimal, linked_order_values: Mapping[str, Decimal], currency: str
) -> AttributionResult:
    """Model B: spend of one creative split across orders explicitly linked to it."""
    if not linked_order_values:
        return AttributionResult(
            allocations={},
            method=AttributionMethod.DIRECT_CREATIVE,
            confidence=Confidence.LOW,
            currency=currency,
            total=spend,
            unallocated=spend,
            note="creative has spend but no linked orders",
            warnings=("no_linked_orders",),
        )
    allocations = allocate_proportionally(spend, linked_order_values, currency)
    return AttributionResult(
        allocations=allocations,
        method=AttributionMethod.DIRECT_CREATIVE,
        confidence=Confidence.HIGH,
        currency=currency,
        total=spend,
        note="explicit ad/video/order link; split within creative by order value",
    )


def proportional(
    spend: Decimal,
    weights: Mapping[str, Decimal],
    currency: str,
    basis: ProportionalBasis = ProportionalBasis.GMV,
) -> AttributionResult:
    """Model C: allocate spend across orders/videos by attributed GMV (MEDIUM) or order count (LOW)."""
    if not weights:
        return AttributionResult(
            allocations={},
            method=AttributionMethod.PROPORTIONAL,
            confidence=Confidence.LOW,
            currency=currency,
            total=spend,
            unallocated=spend,
            note="no attributed entities",
            warnings=("no_weights",),
        )
    allocations = allocate_proportionally(spend, weights, currency)
    warnings: list[str] = []
    confidence = Confidence.MEDIUM if basis is ProportionalBasis.GMV else Confidence.LOW
    if sum(weights.values(), ZERO) == ZERO:
        confidence = Confidence.LOW
        warnings.append("zero_weights_equal_split")
    return AttributionResult(
        allocations=allocations,
        method=AttributionMethod.PROPORTIONAL,
        confidence=confidence,
        currency=currency,
        total=spend,
        note=f"estimated; proportional by {basis.value.lower()}",
        warnings=tuple(warnings),
    )


def blended_ratio(total_ad_spend: Decimal, net_revenue: Decimal) -> Decimal | None:
    """Blended Marketing Cost Ratio = Total Ad Spend / Net Revenue. None when revenue <= 0."""
    if net_revenue <= ZERO:
        return None
    return (total_ad_spend / net_revenue).quantize(RATIO_PLACES)


def blended(
    total_ad_spend: Decimal, net_revenue_by_order: Mapping[str, Decimal], currency: str
) -> AttributionResult:
    """Model D: ratio = spend / total net revenue (all orders, SPEC §6.4-D); spend is then
    allocated by positive net revenue only (negative orders get 0), reconciled to total spend."""
    positive = {k: v for k, v in net_revenue_by_order.items() if v > ZERO}
    net_total = sum(net_revenue_by_order.values(), ZERO)
    ratio = blended_ratio(total_ad_spend, net_total)
    if ratio is None:
        return AttributionResult(
            allocations={k: ZERO for k in net_revenue_by_order},
            method=AttributionMethod.BLENDED,
            confidence=Confidence.LOW,
            currency=currency,
            total=total_ad_spend,
            unallocated=total_ad_spend,
            note="net revenue <= 0; blended ratio undefined",
            warnings=("undefined_ratio",),
        )
    allocations = {k: ZERO for k in net_revenue_by_order}
    allocations.update(allocate_proportionally(total_ad_spend, positive, currency))
    return AttributionResult(
        allocations=allocations,
        method=AttributionMethod.BLENDED,
        confidence=Confidence.LOW,
        currency=currency,
        total=total_ad_spend,
        note=(f"blended marketing cost ratio {ratio} = {total_ad_spend}/{net_total}; "
              "order-level figure is an estimate"),
    )


def roas(kind: RoasKind, revenue: Decimal, spend: Decimal) -> LabeledRoas:
    if spend <= ZERO:
        return LabeledRoas(kind, None)
    return LabeledRoas(kind, (revenue / spend).quantize(RATIO_PLACES))


__all__ = [
    "AllocationError",
    "AttributionMethod",
    "AttributionResult",
    "Confidence",
    "LabeledRoas",
    "ProportionalBasis",
    "RoasKind",
    "allocate_proportionally",
    "blended",
    "blended_ratio",
    "direct_creative",
    "platform_reported",
    "proportional",
    "roas",
]
