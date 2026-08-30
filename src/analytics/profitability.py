"""Deterministic order-level profit engine (SPEC §6, §20, §21). Decimal only, no ORM, no LLM."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from src.analytics.attribution import AttributionMethod, Confidence, allocate_proportionally
from src.analytics.transaction_types import (
    ADJUSTMENT_TYPES,
    SIGN_RULES,
    CurrencyMismatchError,
    NormalizedType,
    SignRule,
    is_platform_fee,
    normalize,
    require_same_currency,
    revenue_effect,
)

ZERO = Decimal(0)


class ProfitStatus(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    SETTLED = "SETTLED"
    PAID = "PAID"
    REFUNDED = "REFUNDED"
    ADJUSTED = "ADJUSTED"


class DuplicateTransactionError(ValueError):
    pass


class CostVersionNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class OrderItemInput:
    order_item_id: str
    sku_id: str
    quantity: int
    unit_sale_price: Decimal
    currency: str
    discounts: Decimal = ZERO  # informational only; profit uses SELLER_DISCOUNT txns

    @property
    def gross_item_value(self) -> Decimal:
        return self.unit_sale_price * self.quantity

    @property
    def net_item_value(self) -> Decimal:
        """Informational (listing view); not used in any profit figure."""
        return self.gross_item_value - self.discounts


@dataclass(frozen=True)
class FinanceTxn:
    external_transaction_id: str
    native_type: str
    amount: Decimal
    currency: str
    normalized_type: NormalizedType | None = None
    order_item_id: str | None = None
    settlement_id: str | None = None
    payout_id: str | None = None

    def __post_init__(self) -> None:
        if self.normalized_type is None:
            object.__setattr__(self, "normalized_type", normalize(self.native_type))

    @property
    def ntype(self) -> NormalizedType:
        assert self.normalized_type is not None
        return self.normalized_type


@dataclass(frozen=True)
class CostVersion:
    sku_id: str
    effective_from: date
    effective_to: date | None
    cogs_per_unit: Decimal
    currency: str
    packaging_per_unit: Decimal = ZERO
    inbound_logistics_per_unit: Decimal = ZERO
    other_variable_cost_per_unit: Decimal = ZERO

    def covers(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on < self.effective_to)


@dataclass(frozen=True)
class AllocatedAds:
    amount: Decimal
    currency: str
    method: AttributionMethod
    confidence: Confidence


@dataclass(frozen=True)
class InternalCosts:
    cogs: Decimal = ZERO
    packaging: Decimal = ZERO
    inbound_logistics: Decimal = ZERO
    other_variable: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.cogs + self.packaging + self.inbound_logistics + self.other_variable


@dataclass(frozen=True)
class RevenueBreakdown:
    sale_proceeds: Decimal = ZERO
    seller_discounts: Decimal = ZERO
    platform_fees: Decimal = ZERO
    affiliate_commission: Decimal = ZERO
    shipping: Decimal = ZERO
    taxes: Decimal = ZERO
    refunds: Decimal = ZERO
    platform_subsidies: Decimal = ZERO
    adjustments: Decimal = ZERO
    unknown_amount: Decimal = ZERO
    unknown_count: int = 0

    @property
    def net_seller_revenue(self) -> Decimal:
        return (
            self.sale_proceeds
            - self.seller_discounts
            - self.platform_fees
            - self.affiliate_commission
            - self.shipping
            - self.taxes
            - self.refunds
            + self.platform_subsidies
            + self.adjustments
        )


@dataclass(frozen=True)
class ItemProfit:
    order_item_id: str
    sku_id: str
    quantity: int
    gross_item_value: Decimal
    net_seller_revenue: Decimal
    costs: InternalCosts
    contribution_profit_before_ads: Decimal
    allocated_ad_cost: Decimal
    estimated_net_profit: Decimal
    cost_version: CostVersion


@dataclass(frozen=True)
class OrderProfit:
    order_id: str
    currency: str
    gross_item_value: Decimal
    revenue: RevenueBreakdown
    net_seller_revenue: Decimal
    costs: InternalCosts
    contribution_profit_before_ads: Decimal
    allocated_ad_cost: Decimal
    estimated_net_profit: Decimal
    profit_status: ProfitStatus
    attribution_method: AttributionMethod | None
    attribution_confidence: Confidence | None
    items: tuple[ItemProfit, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def pick_cost_version(
    versions: Iterable[CostVersion], sku_id: str, order_date: date
) -> CostVersion:
    """Version effective on order_date: effective_from <= d < effective_to (None = open-ended).
    Overlaps resolve to the latest effective_from."""
    matches = [v for v in versions if v.sku_id == sku_id and v.covers(order_date)]
    if not matches:
        raise CostVersionNotFoundError(f"no cost version for {sku_id} on {order_date}")
    return max(matches, key=lambda v: v.effective_from)


def duplicate_transaction_ids(txns: Iterable[FinanceTxn]) -> list[str]:
    counts = Counter(t.external_transaction_id for t in txns)
    return sorted(k for k, n in counts.items() if n > 1)


def dedupe_transactions(txns: Iterable[FinanceTxn]) -> list[FinanceTxn]:
    seen: set[str] = set()
    out: list[FinanceTxn] = []
    for t in txns:
        if t.external_transaction_id not in seen:
            seen.add(t.external_transaction_id)
            out.append(t)
    return out


def _check_currency(txns: Sequence[FinanceTxn], currency: str) -> None:
    for t in txns:
        require_same_currency(currency, t.currency, f"txn {t.external_transaction_id}")


def revenue_breakdown(txns: Sequence[FinanceTxn], currency: str | None = None) -> RevenueBreakdown:
    if not txns:
        return RevenueBreakdown()
    currency = currency or txns[0].currency
    _check_currency(txns, currency)
    b: dict[str, Decimal] = {
        k: ZERO
        for k in (
            "sale_proceeds",
            "seller_discounts",
            "platform_fees",
            "affiliate_commission",
            "shipping",
            "taxes",
            "refunds",
            "platform_subsidies",
            "adjustments",
            "unknown_amount",
        )
    }
    unknown_count = 0
    for t in txns:
        nt = t.ntype
        eff = revenue_effect(nt, t.amount)
        if nt is NormalizedType.UNKNOWN:
            b["unknown_amount"] += t.amount
            unknown_count += 1
        elif nt is NormalizedType.SALE_PROCEEDS:
            b["sale_proceeds"] += eff
        elif nt is NormalizedType.PLATFORM_SUBSIDY:
            b["platform_subsidies"] += eff
        elif nt is NormalizedType.SELLER_DISCOUNT:
            b["seller_discounts"] -= eff
        elif is_platform_fee(nt):
            b["platform_fees"] -= eff
        elif nt is NormalizedType.AFFILIATE_COMMISSION:
            b["affiliate_commission"] -= eff
        elif nt is NormalizedType.SHIPPING_FEE:
            b["shipping"] -= eff
        elif nt is NormalizedType.TAX:
            b["taxes"] -= eff
        elif nt is NormalizedType.REFUND:
            b["refunds"] -= eff
        elif nt in ADJUSTMENT_TYPES:
            b["adjustments"] += eff
    return RevenueBreakdown(unknown_count=unknown_count, **b)


def net_seller_revenue(txns: Sequence[FinanceTxn], currency: str | None = None) -> Decimal:
    return revenue_breakdown(txns, currency).net_seller_revenue


def contribution_profit_before_ads(net_revenue: Decimal, costs: InternalCosts) -> Decimal:
    return net_revenue - costs.total


def estimated_net_profit(contribution: Decimal, allocated_ad_cost: Decimal) -> Decimal:
    return contribution - allocated_ad_cost


def item_costs(item: OrderItemInput, version: CostVersion) -> InternalCosts:
    require_same_currency(item.currency, version.currency, f"cost version {item.sku_id}")
    q = item.quantity
    return InternalCosts(
        cogs=version.cogs_per_unit * q,
        packaging=version.packaging_per_unit * q,
        inbound_logistics=version.inbound_logistics_per_unit * q,
        other_variable=version.other_variable_cost_per_unit * q,
    )


def _sum_costs(parts: Iterable[InternalCosts]) -> InternalCosts:
    parts = list(parts)
    return InternalCosts(
        cogs=sum((p.cogs for p in parts), ZERO),
        packaging=sum((p.packaging for p in parts), ZERO),
        inbound_logistics=sum((p.inbound_logistics for p in parts), ZERO),
        other_variable=sum((p.other_variable for p in parts), ZERO),
    )


def derive_profit_status(txns: Sequence[FinanceTxn], revenue: RevenueBreakdown) -> ProfitStatus:
    """Precedence: REFUNDED > ADJUSTED > PAID > SETTLED > PROVISIONAL.
    ADJUSTED: any adjustment- or REDUCES-type txn (refund, fee, ...) outside the sale's settlements."""
    sales = [t for t in txns if t.ntype is NormalizedType.SALE_PROCEEDS]
    if revenue.sale_proceeds > ZERO and revenue.refunds >= revenue.sale_proceeds:
        return ProfitStatus.REFUNDED
    if not sales or any(t.settlement_id is None for t in sales):
        return ProfitStatus.PROVISIONAL
    sale_settlements = {t.settlement_id for t in sales}
    post_settlement = [
        t for t in txns
        if (t.ntype in ADJUSTMENT_TYPES or SIGN_RULES[t.ntype] is SignRule.REDUCES)
        and t.settlement_id not in sale_settlements
    ]
    if post_settlement:
        return ProfitStatus.ADJUSTED
    if all(t.payout_id is not None for t in sales):
        return ProfitStatus.PAID
    return ProfitStatus.SETTLED


def order_profit(
    order_id: str,
    order_date: date,
    items: Sequence[OrderItemInput],
    txns: Sequence[FinanceTxn],
    cost_versions: Iterable[CostVersion],
    allocated_ads: AllocatedAds | None = None,
) -> OrderProfit:
    if not items:
        raise ValueError("order has no items")
    currency = items[0].currency
    for it in items:
        require_same_currency(currency, it.currency, f"item {it.order_item_id}")
    _check_currency(txns, currency)
    if allocated_ads is not None:
        require_same_currency(currency, allocated_ads.currency, "allocated ads")
    dups = duplicate_transaction_ids(txns)
    if dups:
        raise DuplicateTransactionError(f"duplicate finance transactions: {dups}")

    versions = list(cost_versions)
    revenue = revenue_breakdown(txns, currency)
    net_rev = revenue.net_seller_revenue
    costs_by_item = {
        it.order_item_id: item_costs(it, pick_cost_version(versions, it.sku_id, order_date))
        for it in items
    }
    versions_by_item = {
        it.order_item_id: pick_cost_version(versions, it.sku_id, order_date) for it in items
    }
    costs = _sum_costs(costs_by_item.values())
    contribution = contribution_profit_before_ads(net_rev, costs)
    ad_cost = allocated_ads.amount if allocated_ads else ZERO
    net_profit = estimated_net_profit(contribution, ad_cost)

    weights = {it.order_item_id: it.gross_item_value for it in items}
    item_ids = {it.order_item_id for it in items}
    order_level = [t for t in txns if t.order_item_id not in item_ids]
    item_level = [t for t in txns if t.order_item_id in item_ids]
    unknown_items = sum(1 for t in order_level if t.order_item_id is not None)
    shared_rev = allocate_proportionally(
        net_seller_revenue(order_level, currency), weights, currency
    )
    ad_split = allocate_proportionally(ad_cost, weights, currency)

    item_profits: list[ItemProfit] = []
    for it in items:
        own = [t for t in item_level if t.order_item_id == it.order_item_id]
        rev_i = shared_rev[it.order_item_id] + net_seller_revenue(own, currency)
        c = costs_by_item[it.order_item_id]
        contrib_i = contribution_profit_before_ads(rev_i, c)
        item_profits.append(
            ItemProfit(
                order_item_id=it.order_item_id,
                sku_id=it.sku_id,
                quantity=it.quantity,
                gross_item_value=it.gross_item_value,
                net_seller_revenue=rev_i,
                costs=c,
                contribution_profit_before_ads=contrib_i,
                allocated_ad_cost=ad_split[it.order_item_id],
                estimated_net_profit=estimated_net_profit(contrib_i, ad_split[it.order_item_id]),
                cost_version=versions_by_item[it.order_item_id],
            )
        )

    warnings: list[str] = []
    if revenue.unknown_count:
        warnings.append(f"{revenue.unknown_count} UNKNOWN transactions excluded")
    if unknown_items:
        warnings.append(f"{unknown_items} txns reference unknown order_item_id; allocated order-level")
    status = derive_profit_status(txns, revenue)
    if status is ProfitStatus.PROVISIONAL:
        warnings.append("settlement missing; figures provisional")
    if allocated_ads is None:
        warnings.append("no ad cost allocated")

    return OrderProfit(
        order_id=order_id,
        currency=currency,
        gross_item_value=sum((it.gross_item_value for it in items), ZERO),
        revenue=revenue,
        net_seller_revenue=net_rev,
        costs=costs,
        contribution_profit_before_ads=contribution,
        allocated_ad_cost=ad_cost,
        estimated_net_profit=net_profit,
        profit_status=status,
        attribution_method=allocated_ads.method if allocated_ads else None,
        attribution_confidence=allocated_ads.confidence if allocated_ads else None,
        items=tuple(item_profits),
        warnings=tuple(warnings),
    )


__all__ = [
    "AllocatedAds",
    "CostVersion",
    "CostVersionNotFoundError",
    "CurrencyMismatchError",
    "DuplicateTransactionError",
    "FinanceTxn",
    "InternalCosts",
    "ItemProfit",
    "OrderItemInput",
    "OrderProfit",
    "ProfitStatus",
    "RevenueBreakdown",
    "contribution_profit_before_ads",
    "dedupe_transactions",
    "derive_profit_status",
    "duplicate_transaction_ids",
    "estimated_net_profit",
    "item_costs",
    "net_seller_revenue",
    "order_profit",
    "pick_cost_version",
    "revenue_breakdown",
]
