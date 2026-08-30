"""shop_config.default_cogs_per_unit (fallback COGS for SKUs without a cost version)

Revision ID: e2a5c8d1b7f3
Revises: c7f3a9d2e514
Create Date: 2026-08-31 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e2a5c8d1b7f3'
down_revision: str | Sequence[str] | None = 'c7f3a9d2e514'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shop_config', sa.Column('default_cogs_per_unit', sa.Numeric(precision=20, scale=6),
                                           nullable=True))


def downgrade() -> None:
    op.drop_column('shop_config', 'default_cogs_per_unit')
