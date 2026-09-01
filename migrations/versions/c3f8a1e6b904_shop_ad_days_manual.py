"""shop_ad_days.manual (distinguishes operator-entered Cost from Campaign overview imports)

Revision ID: c3f8a1e6b904
Revises: b7e2c4d9a1f5
Create Date: 2026-09-01 21:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f8a1e6b904'
down_revision: str | Sequence[str] | None = 'b7e2c4d9a1f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shop_ad_days', sa.Column('manual', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE shop_ad_days d SET manual = true FROM source_reports r "
               "WHERE d.report_id = r.id AND r.data->>'scope' = 'manual_entry'")


def downgrade() -> None:
    op.drop_column('shop_ad_days', 'manual')
