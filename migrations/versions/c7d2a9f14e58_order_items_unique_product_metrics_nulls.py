"""order_items unique (order_id, external_item_id); product_metrics unique NULLS NOT DISTINCT (PG16)

Revision ID: c7d2a9f14e58
Revises: b4e7a2c91d03
Create Date: 2026-08-30 23:30:00
"""
from collections.abc import Sequence

from alembic import op

revision: str = 'c7d2a9f14e58'
down_revision: str | Sequence[str] | None = 'b4e7a2c91d03'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_PM_UQ = 'product_metrics_product_id_sku_id_metric_date_key'


def upgrade() -> None:
    # order_items: external_item_id is always populated by the mapper (synthesized when missing);
    # legacy rows without it get a deterministic "<order_id>:<id>" so the constraint can be added.
    op.execute("UPDATE order_items SET external_item_id = order_id::text || ':' || id::text "
               "WHERE external_item_id IS NULL OR external_item_id = ''")
    op.create_unique_constraint('uq_order_items_order_item', 'order_items',
                                ['order_id', 'external_item_id'])
    # product_metrics: drop duplicate product-level rows (sku_id NULL never conflicted), keep newest
    op.execute("DELETE FROM product_metrics a USING product_metrics b "
               "WHERE a.sku_id IS NULL AND b.sku_id IS NULL AND a.product_id = b.product_id "
               "AND a.metric_date = b.metric_date AND a.id < b.id")
    op.drop_constraint(OLD_PM_UQ, 'product_metrics', type_='unique')
    op.create_unique_constraint('uq_product_metrics_product_sku_date', 'product_metrics',
                                ['product_id', 'sku_id', 'metric_date'],
                                postgresql_nulls_not_distinct=True)


def downgrade() -> None:
    op.drop_constraint('uq_product_metrics_product_sku_date', 'product_metrics', type_='unique')
    op.create_unique_constraint(OLD_PM_UQ, 'product_metrics', ['product_id', 'sku_id', 'metric_date'])
    op.drop_constraint('uq_order_items_order_item', 'order_items', type_='unique')
