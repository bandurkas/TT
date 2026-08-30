"""Flat per-order statement records (finance/202309/orders/{id}/statement_transactions),
shop-level daily metrics, and extra columns on settlements/payouts. Imported by models.py."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, PKMixin
from src.db.models import Money, Payout, Ratio, Settlement

# Field names exactly as observed live 2026-08-30 (fixture order_statement_transactions_settled.json)
STATEMENT_AMOUNT_FIELDS: tuple[str, ...] = (
    "gross_sales_amount", "gross_sales_refund_amount", "revenue_amount", "net_sales_amount",
    "seller_discount_amount", "seller_discount_refund_amount", "platform_discount_amount",
    "platform_discount_refund_amount", "after_seller_discounts_subtotal_amount",
    "customer_payment_amount", "customer_refund_amount", "customer_order_refund_amount",
    "fee_amount", "platform_commission_amount", "referral_fee_amount", "transaction_fee_amount",
    "affiliate_commission_amount", "affiliate_commission_before_pit",
    "affiliate_ads_commission_amount", "affiliate_partner_commission_amount",
    "shipping_cost_amount", "shipping_fee_amount", "actual_shipping_fee_amount",
    "customer_shipping_fee_amount", "customer_paid_shipping_fee_amount",
    "customer_paid_shipping_fee_refund_amount", "customer_shipping_fee_offset_amount",
    "platform_shipping_fee_discount_amount", "shipping_fee_subsidy_amount",
    "shipping_cost_discount_amount", "promo_shipping_incentive_amount",
    "shipping_insurance_fee_amount", "signature_confirmation_fee_amount",
    "return_shipping_fee_amount", "actual_return_shipping_fee_amount",
    "refund_administration_fee_amount", "refund_shipping_cost_discount_amount",
    "platform_refund_subsidy_amount", "fbm_shipping_cost_amount", "fbt_fulfillment_fee_amount",
    "fbt_fulfillment_fee_reimbursement_amount", "fbt_shipping_cost_amount",
    "retail_delivery_fee_amount", "retail_delivery_fee_payment_amount",
    "retail_delivery_fee_refund_amount", "sales_tax_amount", "sales_tax_payment_amount",
    "sales_tax_refund_amount", "isr_income_tax_amount", "iva_vat_amount", "pit_amount",
    "adjustment_amount", "settlement_amount",
)


def _amount_columns() -> dict[str, Mapped[Decimal | None]]:
    return {f: mapped_column(Money, nullable=True) for f in STATEMENT_AMOUNT_FIELDS}


class OrderStatementRecord(PKMixin, Base):
    __tablename__ = "order_statement_records"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_order_id: Mapped[str] = mapped_column(String(64))
    external_transaction_id: Mapped[str | None] = mapped_column(String(96))
    statement_id: Mapped[str] = mapped_column(String(96))
    statement_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_create_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str | None] = mapped_column(String(3))
    raw_response_id: Mapped[int | None] = mapped_column(ForeignKey("raw_api_responses.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locals().update(_amount_columns())
    __table_args__ = (UniqueConstraint("shop_id", "external_order_id", "statement_id"),
                      Index("ix_osr_statement", "shop_id", "statement_id"))


class OrderStatementSkuRecord(PKMixin, Base):
    __tablename__ = "order_statement_sku_records"
    record_id: Mapped[int] = mapped_column(ForeignKey("order_statement_records.id"))
    external_sku_id: Mapped[str] = mapped_column(String(64))
    sku_name: Mapped[str | None] = mapped_column(Text)
    product_name: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    locals().update(_amount_columns())
    __table_args__ = (UniqueConstraint("record_id", "external_sku_id"),)


class ShopMetric(PKMixin, Base):
    """analytics/202509/shop/performance per shop-local day."""
    __tablename__ = "shop_metrics"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    gmv_total: Mapped[Decimal | None] = mapped_column(Money)
    gmv_live: Mapped[Decimal | None] = mapped_column(Money)
    gmv_video: Mapped[Decimal | None] = mapped_column(Money)
    gmv_product_card: Mapped[Decimal | None] = mapped_column(Money)
    gross_revenue_gmv_max: Mapped[Decimal | None] = mapped_column(Money)
    gross_revenue_non_gmv_max: Mapped[Decimal | None] = mapped_column(Money)
    gross_revenue_gmv_max_pct: Mapped[Decimal | None] = mapped_column(Ratio)
    sku_orders: Mapped[int | None] = mapped_column(Integer)
    avg_customers: Mapped[Decimal | None] = mapped_column(Ratio)
    currency: Mapped[str | None] = mapped_column(String(3))
    breakdown: Mapped[dict | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("shop_id", "metric_date"),)


# columns added to existing tables (migration adds them in Postgres)
Settlement.extra = mapped_column(JSONB, nullable=True)  # payment_id, payment_status, raw amounts
Payout.payout_type = mapped_column(String(32), nullable=True)  # WITHDRAW|SETTLE|TRANSFER|REVERSE
