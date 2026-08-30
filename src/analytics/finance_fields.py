"""Adapter: TikTok Shop Finance API statement record (flat named-amount fields) -> FinanceTxn list.

Observed live 2026-08-30 (ID shop): GET /finance/202309/orders/{id}/statement_transactions returns one
record per order with ~60 amount fields + sku_statement_transactions[]. Identity (12/12 August orders):
    settlement_amount == revenue_amount + fee_amount + adjustment_amount
    revenue_amount    == gross_sales + seller_discount + gross_sales_refund + seller_discount_refund
    fee_amount        == affiliate_commission + shipping_cost + residual(dynamic commission + order fee)
Decimal only. Unknown fields -> UNKNOWN + warning, never raise. See docs/finance-field-mapping.md.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from src.analytics.profitability import FinanceTxn
from src.analytics.transaction_types import NormalizedType, revenue_effect

log = logging.getLogger(__name__)

ZERO = Decimal(0)


class Role(StrEnum):
    REVENUE = "revenue"  # emitted; SALE_PROCEEDS / SELLER_DISCOUNT
    REFUND = "refund"  # emitted; REFUND / REFUND_FEE_ADJUSTMENT
    FEE = "fee"  # emitted; component of fee_amount (residual absorbs the rest)
    ADJUSTMENT = "adjustment"  # emitted; signed
    AGGREGATE = "aggregate"  # sum of other fields; never emitted (double count)
    PASSTHROUGH = "passthrough"  # customer/platform/logistics money that nets to zero for seller
    INFO = "info"  # buyer-side/derived figures; not part of settlement
    LINKAGE = "linkage"  # ids / status / time / currency
    SKU = "sku"  # per-SKU split + metadata


@dataclass(frozen=True)
class FieldSpec:
    normalized: NormalizedType | None
    role: Role
    note: str = ""


def _f(nt: NormalizedType | None, role: Role, note: str = "") -> FieldSpec:
    return FieldSpec(nt, role, note)


NT = NormalizedType

# Every field observed in the live record (order level; SKU level reuses the same names).
FIELD_MAP: dict[str, FieldSpec] = {
    # --- revenue side
    "gross_sales_amount": _f(NT.SALE_PROCEEDS, Role.REVENUE, "Subtotal before discounts"),
    "seller_discount_amount": _f(NT.SELLER_DISCOUNT, Role.REVENUE, "Seller discounts"),
    "gross_sales_refund_amount": _f(NT.REFUND, Role.REFUND, "Refund subtotal before seller discounts"),
    "seller_discount_refund_amount": _f(
        NT.REFUND_FEE_ADJUSTMENT, Role.REFUND, "Refund of seller discounts (reverses discount)"
    ),
    "revenue_amount": _f(NT.SALE_PROCEEDS, Role.AGGREGATE, "Total Revenue = gross+sdisc+refunds"),
    "net_sales_amount": _f(NT.SALE_PROCEEDS, Role.AGGREGATE, "== revenue_amount in all samples"),
    "after_seller_discounts_subtotal_amount": _f(
        None, Role.INFO, "Subtotal after seller discounts incl. customer shipping (buyer view)"
    ),
    # --- platform-funded discount: customer pays less, platform tops up; revenue unaffected
    "platform_discount_amount": _f(
        NT.PLATFORM_SUBSIDY, Role.INFO, "Platform discount; already inside gross, not emitted"
    ),
    "platform_discount_refund_amount": _f(NT.PLATFORM_SUBSIDY, Role.INFO, "Platform discount refund"),
    "platform_refund_subsidy_amount": _f(NT.PLATFORM_SUBSIDY, Role.INFO, "UNVERIFIED (0 observed)"),
    # --- fee components (all inside fee_amount)
    "fee_amount": _f(None, Role.AGGREGATE, "Total Fees = sum of components + residual"),
    "platform_commission_amount": _f(NT.PLATFORM_COMMISSION, Role.FEE, "0 observed; ID uses residual"),
    "referral_fee_amount": _f(NT.PLATFORM_COMMISSION, Role.FEE, "UNVERIFIED (0 observed)"),
    "transaction_fee_amount": _f(NT.TRANSACTION_FEE, Role.FEE, "UNVERIFIED (0 observed)"),
    "affiliate_commission_amount": _f(NT.AFFILIATE_COMMISSION, Role.FEE, "Affiliate Commission"),
    "affiliate_ads_commission_amount": _f(NT.AFFILIATE_COMMISSION, Role.FEE, "UNVERIFIED (0)"),
    "affiliate_partner_commission_amount": _f(NT.AFFILIATE_COMMISSION, Role.FEE, "UNVERIFIED (0)"),
    "affiliate_commission_before_pit": _f(
        NT.AFFILIATE_COMMISSION, Role.INFO, "== affiliate_commission_amount when PIT=0"
    ),
    "shipping_cost_amount": _f(NT.SHIPPING_FEE, Role.FEE, "Logistics service fee / Shipping cost"),
    "shipping_insurance_fee_amount": _f(NT.SHIPPING_FEE, Role.FEE, "UNVERIFIED (0)"),
    "signature_confirmation_fee_amount": _f(NT.SHIPPING_FEE, Role.FEE, "UNVERIFIED (0)"),
    "return_shipping_fee_amount": _f(NT.SHIPPING_FEE, Role.FEE, "UNVERIFIED (0)"),
    "fbm_shipping_cost_amount": _f(NT.SHIPPING_FEE, Role.FEE, "UNVERIFIED (0)"),
    "fbt_shipping_cost_amount": _f(NT.SHIPPING_FEE, Role.FEE, "UNVERIFIED (0)"),
    "fbt_fulfillment_fee_amount": _f(NT.SERVICE_FEE, Role.FEE, "UNVERIFIED (0)"),
    "fbt_fulfillment_fee_reimbursement_amount": _f(NT.SERVICE_FEE, Role.FEE, "UNVERIFIED (0)"),
    "refund_administration_fee_amount": _f(NT.SERVICE_FEE, Role.FEE, "UNVERIFIED (0)"),
    "retail_delivery_fee_amount": _f(NT.SERVICE_FEE, Role.FEE, "US-only; UNVERIFIED (0)"),
    "sales_tax_amount": _f(NT.TAX, Role.FEE, "UNVERIFIED (0)"),
    "isr_income_tax_amount": _f(NT.TAX, Role.FEE, "Article 22 income tax; UNVERIFIED (0)"),
    "iva_vat_amount": _f(NT.TAX, Role.FEE, "UNVERIFIED (0)"),
    "pit_amount": _f(NT.TAX, Role.FEE, "PIT withheld; UNVERIFIED (0)"),
    # --- adjustment
    "adjustment_amount": _f(NT.OTHER_ADJUSTMENT, Role.ADJUSTMENT, "Adjustment amount (signed)"),
    "settlement_amount": _f(None, Role.AGGREGATE, "Total settlement amount"),
    # --- shipping passthrough: actual + platform_discount + customer (+ customer refund) == 0
    "actual_shipping_fee_amount": _f(None, Role.PASSTHROUGH, "Passed on to logistics provider"),
    "platform_shipping_fee_discount_amount": _f(None, Role.PASSTHROUGH, "Borne by the platform"),
    "customer_shipping_fee_amount": _f(None, Role.PASSTHROUGH, "Paid by the customer"),
    "customer_paid_shipping_fee_amount": _f(None, Role.PASSTHROUGH, "== customer_shipping_fee"),
    "customer_paid_shipping_fee_refund_amount": _f(None, Role.PASSTHROUGH, "Refunded customer ship"),
    "shipping_fee_amount": _f(None, Role.PASSTHROUGH, "== -(customer_shipping_fee + its refund)"),
    "customer_shipping_fee_offset_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "shipping_fee_subsidy_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "shipping_cost_discount_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "refund_shipping_cost_discount_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "promo_shipping_incentive_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "actual_return_shipping_fee_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "retail_delivery_fee_payment_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "retail_delivery_fee_refund_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    "sales_tax_payment_amount": _f(None, Role.PASSTHROUGH, "Customer-paid tax; UNVERIFIED (0)"),
    "sales_tax_refund_amount": _f(None, Role.PASSTHROUGH, "UNVERIFIED (0)"),
    # --- buyer-side info
    "customer_payment_amount": _f(None, Role.INFO, "Customer payment (buyer paid value)"),
    "customer_refund_amount": _f(None, Role.INFO, "Customer refund"),
    "customer_order_refund_amount": _f(None, Role.INFO, "== customer_refund_amount"),
    # --- linkage / sku
    "id": _f(None, Role.LINKAGE, "statement transaction id -> external_transaction_id prefix"),
    "statement_id": _f(None, Role.LINKAGE, "-> FinanceTxn.settlement_id"),
    "statement_time": _f(None, Role.LINKAGE, "unix seconds"),
    "status": _f(None, Role.LINKAGE, "SETTLED -> settlement linkage; else provisional"),
    "currency": _f(None, Role.LINKAGE, ""),
    "sku_statement_transactions": _f(None, Role.SKU, "exact per-SKU split"),
    "sku_id": _f(None, Role.SKU, ""),
    "sku_name": _f(None, Role.SKU, ""),
    "product_name": _f(None, Role.SKU, ""),
    "quantity": _f(None, Role.SKU, ""),
}

EMITTED_ROLES = frozenset({Role.REVENUE, Role.REFUND, Role.FEE, Role.ADJUSTMENT})
RESIDUAL_NOTE = "dynamic commission + order processing fee (residual)"
RESIDUAL_FIELD = "fee_residual"
SETTLED_STATUSES = frozenset({"SETTLED", "PAID"})


class StatementKind(StrEnum):
    AD_DEDUCTION = "AD_DEDUCTION"
    ORDER_SETTLEMENT = "ORDER_SETTLEMENT"
    OTHER = "OTHER"


@dataclass(frozen=True)
class StatementLinkage:
    record_id: str
    statement_id: str | None
    statement_time: int | None
    status: str
    currency: str
    settled: bool


class TxnList(list[FinanceTxn]):
    """Emitted txns + `mismatch` = settlement_amount - sum(revenue_effect over non-UNKNOWN txns);
    None when they agree. Caller persists a non-None value to analytics_reconciliation."""
    mismatch: Decimal | None = None


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, (bool, dict, list)):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def amount(record: Mapping[str, Any], field: str) -> Decimal:
    d = _dec(record.get(field))
    return d if d is not None else ZERO


def statement_linkage(record: Mapping[str, Any]) -> StatementLinkage:
    status = str(record.get("status") or "").upper()
    sid = record.get("statement_id")
    st = record.get("statement_time")
    return StatementLinkage(
        record_id=str(record.get("id") or ""),
        statement_id=str(sid) if sid else None,
        statement_time=int(st) if isinstance(st, (int, str)) and str(st).isdigit() else None,
        status=status,
        currency=str(record.get("currency") or ""),
        settled=status in SETTLED_STATUSES and bool(sid),
    )


def identity_holds(record: Mapping[str, Any]) -> bool:
    a = amount
    return a(record, "settlement_amount") == (
        a(record, "revenue_amount") + a(record, "fee_amount") + a(record, "adjustment_amount")
    )


def shipping_passthrough_net(record: Mapping[str, Any]) -> Decimal:
    """Seller-neutral shipping money; expected == 0."""
    a = amount
    return (
        a(record, "actual_shipping_fee_amount")
        + a(record, "platform_shipping_fee_discount_amount")
        + a(record, "customer_shipping_fee_amount")
        + a(record, "customer_paid_shipping_fee_refund_amount")
    )


def _emit(
    record: Mapping[str, Any],
    *,
    prefix: str,
    currency: str,
    settlement_id: str | None,
    payout_id: str | None,
    order_item_id: str | None,
    ctx: str,
) -> list[FinanceTxn]:
    out: list[FinanceTxn] = []
    fee_components = ZERO

    def add(field: str, nt: NormalizedType, amt: Decimal, note: str | None = None) -> None:
        out.append(
            FinanceTxn(
                external_transaction_id=f"{prefix}:{field}",
                native_type=field,
                amount=amt,
                currency=currency,
                normalized_type=nt,
                order_item_id=order_item_id,
                settlement_id=settlement_id,
                payout_id=payout_id,
                note=note,
            )
        )

    for field, raw in record.items():
        spec = FIELD_MAP.get(field)
        if spec is None:
            amt = _dec(raw)
            if amt is None:
                log.warning("finance_fields: unknown non-amount field %r (%s) ignored", field, ctx)
                continue
            log.warning("finance_fields: unknown field %r=%s (%s) -> UNKNOWN", field, amt, ctx)
            if amt != ZERO:
                add(field, NormalizedType.UNKNOWN, amt)
            continue
        if spec.role not in EMITTED_ROLES:
            continue
        amt = _dec(raw)
        if amt is None:
            log.warning("finance_fields: non-decimal %r=%r (%s) skipped", field, raw, ctx)
            continue
        if spec.role is Role.FEE:
            fee_components += amt
        if amt == ZERO:
            continue
        assert spec.normalized is not None
        add(field, spec.normalized, amt)

    residual = amount(record, "fee_amount") - fee_components
    if residual != ZERO:
        add(RESIDUAL_FIELD, NormalizedType.PLATFORM_COMMISSION, residual, RESIDUAL_NOTE)
    return out


def statement_record_to_txns(
    record: Mapping[str, Any],
    order_id: str,
    *,
    sku_to_item: Mapping[str, str] | None = None,
    payout_id: str | None = None,
) -> TxnList:
    """Flat statement record -> component FinanceTxns; engine net_seller_revenue == settlement_amount.

    Per-SKU rows are used when they exactly sum to the order record (order_item_id = sku_to_item[sku]
    or sku_id); otherwise order-level txns are emitted and the engine splits proportionally.
    Residual fee (fee_amount - known components) -> PLATFORM_COMMISSION `fee_residual`.
    Result `.mismatch` (settlement_amount - sum of non-UNKNOWN revenue effects) is None when the
    emitted txns reproduce settlement_amount; otherwise logged at ERROR.
    """
    out = TxnList(_record_txns(record, order_id, sku_to_item=sku_to_item, payout_id=payout_id))
    total = sum((revenue_effect(t.ntype, t.amount) for t in out
                 if t.ntype is not NormalizedType.UNKNOWN), ZERO)
    delta = amount(record, "settlement_amount") - total
    if delta != ZERO:
        out.mismatch = delta
        log.error("finance_fields: order %s emitted txns sum %s != settlement_amount %s (delta %s)",
                  order_id, total, amount(record, "settlement_amount"), delta)
    return out


def _record_txns(
    record: Mapping[str, Any],
    order_id: str,
    *,
    sku_to_item: Mapping[str, str] | None,
    payout_id: str | None,
) -> list[FinanceTxn]:
    link = statement_linkage(record)
    settlement_id = link.statement_id if link.settled else None
    # id fallback: two records for one order (e.g. settled + restated) must not collide
    prefix = link.record_id or (f"{order_id}:{link.statement_id}" if link.statement_id else order_id)
    currency = link.currency
    if not identity_holds(record):
        log.warning("finance_fields: identity broken for order %s (%s)", order_id, prefix)

    skus = record.get("sku_statement_transactions")
    if isinstance(skus, list) and skus and _skus_exact(record, skus):
        out: list[FinanceTxn] = []
        for i, s in enumerate(skus):
            sku_id = str(s.get("sku_id") or f"sku{i}")
            item_id = (sku_to_item or {}).get(sku_id, sku_id)
            out.extend(
                _emit(
                    s,
                    prefix=f"{prefix}:{sku_id}",
                    currency=str(s.get("currency") or currency),
                    settlement_id=settlement_id,
                    payout_id=payout_id,
                    order_item_id=item_id,
                    ctx=f"order {order_id} sku {sku_id}",
                )
            )
        return out
    return _emit(
        record,
        prefix=prefix,
        currency=currency,
        settlement_id=settlement_id,
        payout_id=payout_id,
        order_item_id=None,
        ctx=f"order {order_id}",
    )


def _skus_exact(record: Mapping[str, Any], skus: list[Any]) -> bool:
    if not all(isinstance(s, Mapping) for s in skus):
        return False
    for key in ("settlement_amount", "revenue_amount", "fee_amount", "adjustment_amount"):
        if sum((amount(s, key) for s in skus), ZERO) != amount(record, key):
            return False
    return True


_EXPORT_KEYS = {
    "revenue_amount": ("Total Revenue",),
    "fee_amount": ("Total Fees",),
    "adjustment_amount": ("Adjustment amount",),
}


def _stmt_amount(stmt: Mapping[str, Any], key: str) -> Decimal:
    if key in stmt:
        return amount(stmt, key)
    for alt in _EXPORT_KEYS.get(key, ()):
        if alt in stmt:
            return amount(stmt, alt)
    return ZERO


def classify_statement(statement: Mapping[str, Any]) -> StatementKind:
    """Statements list row (API keys or Seller Center export columns).
    revenue==0 & fee==0 & adjustment<0 -> AD_DEDUCTION candidate (confirm vs export amounts/dates).
    """
    rev = _stmt_amount(statement, "revenue_amount")
    fee = _stmt_amount(statement, "fee_amount")
    adj = _stmt_amount(statement, "adjustment_amount")
    ttype = str(statement.get("Transaction type") or "")
    if "ads" in ttype.lower():
        return StatementKind.AD_DEDUCTION
    if rev == ZERO and fee == ZERO and adj < ZERO:
        return StatementKind.AD_DEDUCTION
    if rev != ZERO or fee != ZERO:
        return StatementKind.ORDER_SETTLEMENT
    return StatementKind.OTHER


__all__ = [
    "EMITTED_ROLES",
    "FIELD_MAP",
    "RESIDUAL_FIELD",
    "RESIDUAL_NOTE",
    "FieldSpec",
    "Role",
    "StatementKind",
    "StatementLinkage",
    "TxnList",
    "amount",
    "classify_statement",
    "identity_holds",
    "shipping_passthrough_net",
    "statement_linkage",
    "statement_record_to_txns",
]
