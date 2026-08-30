"""order_statement_records, order_statement_sku_records, shop_metrics; settlements.extra,
payouts.payout_type

Revision ID: b4e7a2c91d03
Revises: 8d1c1fc758d5
Create Date: 2026-08-30 22:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b4e7a2c91d03'
down_revision: str | Sequence[str] | None = '8d1c1fc758d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AMOUNT_FIELDS = (
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


def _amount_cols() -> list[sa.Column]:
    return [sa.Column(f, sa.Numeric(precision=20, scale=6), nullable=True) for f in AMOUNT_FIELDS]


def upgrade() -> None:
    op.create_table(
        'order_statement_records',
        sa.Column('shop_id', sa.BigInteger(), nullable=False),
        sa.Column('external_order_id', sa.String(length=64), nullable=False),
        sa.Column('external_transaction_id', sa.String(length=96), nullable=True),
        sa.Column('statement_id', sa.String(length=96), nullable=False),
        sa.Column('statement_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('order_create_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('raw_response_id', sa.BigInteger(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        *_amount_cols(),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(['raw_response_id'], ['raw_api_responses.id']),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'external_order_id', 'statement_id'),
    )
    op.create_index('ix_osr_statement', 'order_statement_records', ['shop_id', 'statement_id'])
    op.create_table(
        'order_statement_sku_records',
        sa.Column('record_id', sa.BigInteger(), nullable=False),
        sa.Column('external_sku_id', sa.String(length=64), nullable=False),
        sa.Column('sku_name', sa.Text(), nullable=True),
        sa.Column('product_name', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        *_amount_cols(),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(['record_id'], ['order_statement_records.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('record_id', 'external_sku_id'),
    )
    op.create_table(
        'shop_metrics',
        sa.Column('shop_id', sa.BigInteger(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('gmv_total', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('gmv_live', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('gmv_video', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('gmv_product_card', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('gross_revenue_gmv_max', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('gross_revenue_non_gmv_max', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('gross_revenue_gmv_max_pct', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('sku_orders', sa.Integer(), nullable=True),
        sa.Column('avg_customers', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'metric_date'),
    )
    op.add_column('settlements', sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()),
                                           nullable=True))
    op.add_column('payouts', sa.Column('payout_type', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('payouts', 'payout_type')
    op.drop_column('settlements', 'extra')
    op.drop_table('shop_metrics')
    op.drop_table('order_statement_sku_records')
    op.drop_index('ix_osr_statement', table_name='order_statement_records')
    op.drop_table('order_statement_records')
