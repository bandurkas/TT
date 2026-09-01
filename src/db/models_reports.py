"""Audited Seller Center exports; payments never populate advertising Cost."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, PKMixin
from src.db.models import Money


class SourceReport(PKMixin, Base):
    __tablename__ = "source_reports"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    kind: Mapped[str] = mapped_column(String(24))
    sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("shop_id", "kind", "sha256"),)


class ShopAdDay(PKMixin, Base):
    __tablename__ = "shop_ad_days"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    report_id: Mapped[int] = mapped_column(ForeignKey("source_reports.id"))
    currency: Mapped[str] = mapped_column(String(3))
    cost: Mapped[Decimal] = mapped_column(Money)
    sku_orders: Mapped[int] = mapped_column(Integer)
    gross_revenue: Mapped[Decimal] = mapped_column(Money)
    partial: Mapped[bool] = mapped_column(Boolean)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("shop_id", "metric_date"),)
