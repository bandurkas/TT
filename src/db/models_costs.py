"""Product cost batches (purchase lots). Rebuilt into sku_cost_versions (date-effective) by FIFO."""
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, PKMixin, TimestampMixin
from src.db.models import Money


class CostBatch(PKMixin, TimestampMixin, Base):
    __tablename__ = "cost_batches"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    scope: Mapped[str] = mapped_column(String(8))  # all | product | sku
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("skus.id"))
    received_on: Mapped[date] = mapped_column(Date)  # first day this lot is sold from
    unit_cost: Mapped[Decimal] = mapped_column(Money)
    quantity: Mapped[int | None] = mapped_column(Integer)  # units in the lot; None = until next lot
    currency: Mapped[str] = mapped_column(String(3))
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (Index("ix_cost_batches_shop_from", "shop_id", "received_on"),)
