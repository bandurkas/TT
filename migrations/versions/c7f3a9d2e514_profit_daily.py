"""analytics_shop_daily, analytics_product_daily (profit job aggregates)

Revision ID: c7f3a9d2e514
Revises: b4e7a2c91d03
Create Date: 2026-08-30 23:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7f3a9d2e514'
down_revision: str | Sequence[str] | None = 'c7d2a9f14e58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = ("gmv", "net_seller_revenue", "fees", "affiliate", "cogs", "contribution", "ad_cost",
         "net_profit", "refunds")


def _daily_cols() -> list[sa.Column]:
    cols = [sa.Column('orders', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('units', sa.Integer(), nullable=False, server_default='0')]
    cols += [sa.Column(m, sa.Numeric(precision=20, scale=6), nullable=False, server_default='0')
             for m in MONEY]
    cols += [sa.Column('net_margin', sa.Numeric(precision=12, scale=6), nullable=True),
             sa.Column('settled_orders', sa.Integer(), nullable=False, server_default='0'),
             sa.Column('provisional_orders', sa.Integer(), nullable=False, server_default='0'),
             sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False)]
    return cols


def upgrade() -> None:
    op.create_table(
        'analytics_shop_daily',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('shop_id', sa.BigInteger(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        *_daily_cols(),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'metric_date'),
    )
    op.create_table(
        'analytics_product_daily',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        *_daily_cols(),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'metric_date'),
    )


def downgrade() -> None:
    op.drop_table('analytics_product_daily')
    op.drop_table('analytics_shop_daily')
