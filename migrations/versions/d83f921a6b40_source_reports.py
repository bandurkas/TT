"""Audited report imports and advertising coverage."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d83f921a6b40"
down_revision = "a9c4e7f1b2d3"
branch_labels = depends_on = None


def upgrade():
    op.create_table("source_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("shop_id", "kind", "sha256"))
    op.create_table("shop_ad_days",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("report_id", sa.BigInteger(), sa.ForeignKey("source_reports.id"), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("cost", sa.Numeric(20, 6), nullable=False),
        sa.Column("sku_orders", sa.Integer(), nullable=False),
        sa.Column("gross_revenue", sa.Numeric(20, 6), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("shop_id", "metric_date"))
    for table in ("analytics_shop_daily", "analytics_product_daily"):
        op.add_column(table, sa.Column("profit_inputs_known", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        op.add_column(table, sa.Column("ad_cost_known", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        op.add_column(table, sa.Column("ad_cost_partial", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade():
    for table in ("analytics_shop_daily", "analytics_product_daily"):
        op.drop_column(table, "profit_inputs_known")
        op.drop_column(table, "ad_cost_partial")
        op.drop_column(table, "ad_cost_known")
    op.drop_table("shop_ad_days")
    op.drop_table("source_reports")
