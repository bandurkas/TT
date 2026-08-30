"""video_products (links) + video_product_metrics (per video × product × day)

Revision ID: a9c4e7f1b2d3
Revises: e2a5c8d1b7f3
Create Date: 2026-08-31 13:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a9c4e7f1b2d3'
down_revision: str | Sequence[str] | None = 'e2a5c8d1b7f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'video_products',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('video_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('first_seen', sa.Date(), nullable=False),
        sa.Column('last_seen', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('video_id', 'product_id'),
    )
    op.create_index('ix_video_products_video_id', 'video_products', ['video_id'])
    op.create_index('ix_video_products_product_id', 'video_products', ['product_id'])
    op.create_table(
        'video_product_metrics',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('video_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('impressions', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('clicks', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('ctr', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('customers', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('units_sold', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gmv', sa.Numeric(precision=20, scale=6), nullable=False, server_default='0'),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('video_id', 'product_id', 'metric_date'),
    )
    op.create_index('ix_video_product_metrics_video_id', 'video_product_metrics', ['video_id'])
    op.create_index('ix_video_product_metrics_product_id', 'video_product_metrics', ['product_id'])


def downgrade() -> None:
    op.drop_index('ix_video_product_metrics_product_id', table_name='video_product_metrics')
    op.drop_index('ix_video_product_metrics_video_id', table_name='video_product_metrics')
    op.drop_table('video_product_metrics')
    op.drop_index('ix_video_products_product_id', table_name='video_products')
    op.drop_index('ix_video_products_video_id', table_name='video_products')
    op.drop_table('video_products')
