"""Daily profit aggregates (shop / product) computed from current analytics_order_profit rows.
Imported by models_finance.py so Base.metadata sees the tables."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, PKMixin
from src.db.models import Money, Ratio

MONEY_COLUMNS: tuple[str, ...] = (
    "gmv", "net_seller_revenue", "fees", "affiliate", "cogs", "contribution", "ad_cost",
    "net_profit", "refunds",
)


class _DailyMoney:
    profit_inputs_known: Mapped[bool] = mapped_column(Boolean, default=False)
    ad_cost_known: Mapped[bool] = mapped_column(Boolean, default=False)
    ad_cost_partial: Mapped[bool] = mapped_column(Boolean, default=False)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[int] = mapped_column(Integer, default=0)
    gmv: Mapped[Decimal] = mapped_column(Money, default=0)
    net_seller_revenue: Mapped[Decimal] = mapped_column(Money, default=0)
    fees: Mapped[Decimal] = mapped_column(Money, default=0)  # platform + seller shipping + taxes
    affiliate: Mapped[Decimal] = mapped_column(Money, default=0)
    cogs: Mapped[Decimal] = mapped_column(Money, default=0)  # incl. packaging/inbound/other
    contribution: Mapped[Decimal] = mapped_column(Money, default=0)
    ad_cost: Mapped[Decimal] = mapped_column(Money, default=0)  # BLENDED estimate, LOW confidence
    net_profit: Mapped[Decimal] = mapped_column(Money, default=0)
    net_margin: Mapped[Decimal | None] = mapped_column(Ratio)  # net_profit / net_seller_revenue
    refunds: Mapped[Decimal] = mapped_column(Money, default=0)
    settled_orders: Mapped[int] = mapped_column(Integer, default=0)
    provisional_orders: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ShopDaily(PKMixin, _DailyMoney, Base):
    __tablename__ = "analytics_shop_daily"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (UniqueConstraint("shop_id", "metric_date"),)


class ProductDaily(PKMixin, _DailyMoney, Base):
    __tablename__ = "analytics_product_daily"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (UniqueConstraint("product_id", "metric_date"),)
