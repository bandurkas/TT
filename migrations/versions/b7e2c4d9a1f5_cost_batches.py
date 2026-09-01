"""cost_batches: purchase lots with unit cost and optional quantity (FIFO -> sku_cost_versions)

Revision ID: b7e2c4d9a1f5
Revises: d83f921a6b40
Create Date: 2026-09-01 20:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e2c4d9a1f5'
down_revision: str | Sequence[str] | None = 'd83f921a6b40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'cost_batches',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('shop_id', sa.BigInteger(), nullable=False),
        sa.Column('scope', sa.String(length=8), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=True),
        sa.Column('sku_id', sa.BigInteger(), nullable=True),
        sa.Column('received_on', sa.Date(), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.ForeignKeyConstraint(['sku_id'], ['skus.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cost_batches_shop_from', 'cost_batches', ['shop_id', 'received_on'])


def downgrade() -> None:
    op.drop_index('ix_cost_batches_shop_from', table_name='cost_batches')
    op.drop_table('cost_batches')
