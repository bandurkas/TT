"""Normalized + analytics schema per SPEC §5, §13, §17, §18, §19, §26, §27, §28.
Money: Numeric(20,6) + currency. Timestamps: UTC timestamptz. metric_date: shop-local date."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, PKMixin, TimestampMixin

Money = Numeric(20, 6)
Ratio = Numeric(12, 6)


# --- raw layer -------------------------------------------------------------
class RawApiResponse(PKMixin, Base):
    __tablename__ = "raw_api_responses"
    integration: Mapped[str] = mapped_column(String(32))  # tiktok_shop | tiktok_ads
    resource: Mapped[str] = mapped_column(String(64))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"))
    request_meta: Mapped[dict] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_raw_resource_fetched", "integration", "resource", "fetched_at"),)


class IntegrationSyncState(PKMixin, Base):
    __tablename__ = "integration_sync_state"
    integration: Mapped[str] = mapped_column(String(32))
    resource_type: Mapped[str] = mapped_column(String(64))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"))
    cursor: Mapped[str | None] = mapped_column(Text)
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="idle")
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("integration", "resource_type", "shop_id"),)


# --- core commerce ---------------------------------------------------------
class Shop(PKMixin, TimestampMixin, Base):
    __tablename__ = "shops"
    platform: Mapped[str] = mapped_column(String(32), default="tiktok_shop")
    external_shop_id: Mapped[str] = mapped_column(String(64))
    shop_cipher: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32), default="active")
    __table_args__ = (UniqueConstraint("platform", "external_shop_id"),)


class ShopConfig(PKMixin, TimestampMixin, Base):
    __tablename__ = "shop_config"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), unique=True)
    minimum_net_margin: Mapped[Decimal] = mapped_column(Ratio, default=Decimal("0.10"))
    minimum_profit_per_order: Mapped[Decimal] = mapped_column(Money, default=0)
    max_acceptable_cpa: Mapped[Decimal | None] = mapped_column(Money)
    minimum_sample_impressions: Mapped[int] = mapped_column(Integer, default=2000)
    minimum_sample_clicks: Mapped[int] = mapped_column(Integer, default=50)
    minimum_sample_orders: Mapped[int] = mapped_column(Integer, default=5)
    alert_cooldown_minutes: Mapped[int] = mapped_column(Integer, default=360)
    report_time_local: Mapped[str] = mapped_column(String(5), default="08:00")
    operating_mode: Mapped[str] = mapped_column(String(32), default="MODE_2")  # SPEC §31
    default_cogs_per_unit: Mapped[Decimal | None] = mapped_column(Money)  # fallback for SKUs w/o cost version
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class Product(PKMixin, TimestampMixin, Base):
    __tablename__ = "products"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_product_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (UniqueConstraint("shop_id", "external_product_id"),)


class Sku(PKMixin, TimestampMixin, Base):
    __tablename__ = "skus"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    external_sku_id: Mapped[str] = mapped_column(String(64))
    seller_sku: Mapped[str | None] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    variation_data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("product_id", "external_sku_id"),)


class SkuCostVersion(PKMixin, TimestampMixin, Base):
    __tablename__ = "sku_cost_versions"
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    cogs_per_unit: Mapped[Decimal] = mapped_column(Money)
    packaging_per_unit: Mapped[Decimal] = mapped_column(Money, default=0)
    inbound_logistics_per_unit: Mapped[Decimal] = mapped_column(Money, default=0)
    other_variable_cost_per_unit: Mapped[Decimal] = mapped_column(Money, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("ix_cost_sku_from", "sku_id", "effective_from"),)


class Creator(PKMixin, TimestampMixin, Base):
    __tablename__ = "creators"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_creator_id: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(255))
    account_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("shop_id", "external_creator_id"),)


class Video(PKMixin, TimestampMixin, Base):
    __tablename__ = "videos"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_video_id: Mapped[str] = mapped_column(String(64))
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("creators.id"))
    account_type: Mapped[str] = mapped_column(String(16), default="unknown")  # official|marketing|affiliate|unknown
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    caption: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(32))
    video_reference: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("shop_id", "external_video_id"),)


class Order(PKMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_order_id: Mapped[str] = mapped_column(String(64))
    order_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_status: Mapped[str] = mapped_column(String(32), index=True)
    buyer_paid_amount: Mapped[Decimal | None] = mapped_column(Money)
    gross_merchandise_value: Mapped[Decimal | None] = mapped_column(Money)
    seller_discount: Mapped[Decimal] = mapped_column(Money, default=0)
    platform_discount: Mapped[Decimal] = mapped_column(Money, default=0)
    shipping_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    raw_source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("shop_id", "external_order_id"),)


class OrderItem(PKMixin, Base):
    __tablename__ = "order_items"
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    external_item_id: Mapped[str | None] = mapped_column(String(64))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("skus.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_list_price: Mapped[Decimal | None] = mapped_column(Money)
    unit_sale_price: Mapped[Decimal | None] = mapped_column(Money)
    gross_item_value: Mapped[Decimal | None] = mapped_column(Money)
    discounts: Mapped[Decimal] = mapped_column(Money, default=0)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("creators.id"))
    source_video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"))
    attribution_source: Mapped[str | None] = mapped_column(String(32))  # api|derived|none
    __table_args__ = (UniqueConstraint("order_id", "external_item_id",
                                       name="uq_order_items_order_item"),)


# --- finance ---------------------------------------------------------------
class FinanceTransaction(PKMixin, Base):
    __tablename__ = "finance_transactions"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_transaction_id: Mapped[str] = mapped_column(String(96))
    external_order_id: Mapped[str | None] = mapped_column(String(64), index=True)
    order_item_id: Mapped[int | None] = mapped_column(ForeignKey("order_items.id"))
    native_type: Mapped[str] = mapped_column(String(96))
    normalized_type: Mapped[str] = mapped_column(String(48), default="UNKNOWN")
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    transaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("settlements.id"))
    payout_id: Mapped[int | None] = mapped_column(ForeignKey("payouts.id"))
    status: Mapped[str | None] = mapped_column(String(32))
    raw_response_id: Mapped[int | None] = mapped_column(ForeignKey("raw_api_responses.id"))
    __table_args__ = (UniqueConstraint("shop_id", "external_transaction_id"),)


class Settlement(PKMixin, Base):
    __tablename__ = "settlements"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_settlement_id: Mapped[str] = mapped_column(String(96))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gross_amount: Mapped[Decimal | None] = mapped_column(Money)
    deductions: Mapped[Decimal | None] = mapped_column(Money)
    net_amount: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str | None] = mapped_column(String(32))
    settlement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("shop_id", "external_settlement_id"),)


class Payout(PKMixin, Base):
    __tablename__ = "payouts"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    external_payout_id: Mapped[str] = mapped_column(String(96))
    payout_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    payout_status: Mapped[str | None] = mapped_column(String(32))
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bank_reference: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (UniqueConstraint("shop_id", "external_payout_id"),)


# --- metrics (time series snapshots) ---------------------------------------
class VideoProduct(PKMixin, Base):
    """Video -> product links from video performance API `products[]` (which listings a video sells)."""
    __tablename__ = "video_products"
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date)
    __table_args__ = (UniqueConstraint("video_id", "product_id"),)


class VideoProductMetric(PKMixin, Base):
    """Per video × product × day from `shop_videos/{id}/performance` sales.breakdowns
    (live-verified 2026-08-31): real product impressions/clicks a video sends to each listing."""
    __tablename__ = "video_product_metrics"
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    metric_date: Mapped[date] = mapped_column(Date)
    impressions: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Ratio)
    customers: Mapped[int] = mapped_column(Integer, default=0)
    units_sold: Mapped[int] = mapped_column(Integer, default=0)
    gmv: Mapped[Decimal] = mapped_column(Money, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("video_id", "product_id", "metric_date"),)


class VideoMetric(PKMixin, Base):
    __tablename__ = "video_metrics"
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    metric_hour: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    product_clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Ratio)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    units_sold: Mapped[int] = mapped_column(Integer, default=0)
    gmv: Mapped[Decimal] = mapped_column(Money, default=0)
    gpm: Mapped[Decimal | None] = mapped_column(Money)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Ratio)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("video_id", "metric_date", "metric_hour"),)


class CreatorMetric(PKMixin, Base):
    __tablename__ = "creator_metrics"
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    videos_count: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[int] = mapped_column(Integer, default=0)
    gmv: Mapped[Decimal] = mapped_column(Money, default=0)
    commission: Mapped[Decimal] = mapped_column(Money, default=0)
    estimated_profit: Mapped[Decimal | None] = mapped_column(Money)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("creator_id", "metric_date"),)


class ProductMetric(PKMixin, Base):
    __tablename__ = "product_metrics"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("skus.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[int] = mapped_column(Integer, default=0)
    gmv: Mapped[Decimal] = mapped_column(Money, default=0)
    refunds: Mapped[Decimal] = mapped_column(Money, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # PG16 NULLS NOT DISTINCT: product-level rows (sku_id NULL) must conflict on upsert
    __table_args__ = (UniqueConstraint("product_id", "sku_id", "metric_date",
                                       name="uq_product_metrics_product_sku_date",
                                       postgresql_nulls_not_distinct=True),)


# --- ads -------------------------------------------------------------------
class AdAccount(PKMixin, TimestampMixin, Base):
    __tablename__ = "ad_accounts"
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"))
    external_advertiser_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    currency: Mapped[str | None] = mapped_column(String(3))
    timezone: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(32))


class Campaign(PKMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"
    ad_account_id: Mapped[int] = mapped_column(ForeignKey("ad_accounts.id"))
    external_campaign_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255))
    objective: Mapped[str | None] = mapped_column(String(64))
    campaign_type: Mapped[str | None] = mapped_column(String(64))  # e.g. GMV_MAX
    status: Mapped[str | None] = mapped_column(String(32))
    budget: Mapped[Decimal | None] = mapped_column(Money)
    budget_mode: Mapped[str | None] = mapped_column(String(32))
    settings: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("ad_account_id", "external_campaign_id"),)


class AdGroup(PKMixin, TimestampMixin, Base):
    __tablename__ = "ad_groups"
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    external_adgroup_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(32))
    budget: Mapped[Decimal | None] = mapped_column(Money)
    optimization_goal: Mapped[str | None] = mapped_column(String(64))
    settings: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("campaign_id", "external_adgroup_id"),)


class Ad(PKMixin, TimestampMixin, Base):
    __tablename__ = "ads"
    ad_group_id: Mapped[int] = mapped_column(ForeignKey("ad_groups.id"))
    external_ad_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("ad_group_id", "external_ad_id"),)


class AdCreative(PKMixin, TimestampMixin, Base):
    __tablename__ = "ad_creatives"
    ad_id: Mapped[int | None] = mapped_column(ForeignKey("ads.id"))
    external_creative_id: Mapped[str] = mapped_column(String(64), unique=True)
    external_video_id: Mapped[str | None] = mapped_column(String(64), index=True)
    creative_type: Mapped[str | None] = mapped_column(String(32))
    meta: Mapped[dict | None] = mapped_column(JSONB)


class CreativeMapping(PKMixin, TimestampMixin, Base):
    __tablename__ = "creative_mappings"
    ad_creative_id: Mapped[int] = mapped_column(ForeignKey("ad_creatives.id"))
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("skus.id"))
    mapping_source: Mapped[str] = mapped_column(String(32))  # api_id|heuristic|manual
    confidence: Mapped[Decimal] = mapped_column(Ratio)
    __table_args__ = (UniqueConstraint("ad_creative_id", "video_id", "product_id", "sku_id"),)


class AdMetric(PKMixin, Base):
    __tablename__ = "ad_metrics"
    entity_type: Mapped[str] = mapped_column(String(16))  # campaign|adgroup|ad|creative
    entity_id: Mapped[int] = mapped_column(BigInteger)
    metric_date: Mapped[date] = mapped_column(Date)
    metric_hour: Mapped[int | None] = mapped_column(Integer)
    spend: Mapped[Decimal] = mapped_column(Money, default=0)
    impressions: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Ratio)
    cpc: Mapped[Decimal | None] = mapped_column(Money)
    cpm: Mapped[Decimal | None] = mapped_column(Money)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    attributed_orders: Mapped[int] = mapped_column(Integer, default=0)
    attributed_gmv: Mapped[Decimal] = mapped_column(Money, default=0)
    reported_roas: Mapped[Decimal | None] = mapped_column(Ratio)
    currency: Mapped[str | None] = mapped_column(String(3))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "metric_date", "metric_hour"),)


# --- analytics layer -------------------------------------------------------
class OrderProfit(PKMixin, Base):
    """Calculated per order, versioned (SPEC §6.3, §20)."""
    __tablename__ = "analytics_order_profit"
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    profit_status: Mapped[str] = mapped_column(String(16))
    sale_proceeds: Mapped[Decimal] = mapped_column(Money, default=0)
    seller_discounts: Mapped[Decimal] = mapped_column(Money, default=0)
    platform_fees: Mapped[Decimal] = mapped_column(Money, default=0)
    affiliate_commission: Mapped[Decimal] = mapped_column(Money, default=0)
    seller_shipping: Mapped[Decimal] = mapped_column(Money, default=0)
    taxes: Mapped[Decimal] = mapped_column(Money, default=0)
    refunds: Mapped[Decimal] = mapped_column(Money, default=0)
    subsidies: Mapped[Decimal] = mapped_column(Money, default=0)
    adjustments: Mapped[Decimal] = mapped_column(Money, default=0)
    net_seller_revenue: Mapped[Decimal] = mapped_column(Money)
    cogs: Mapped[Decimal] = mapped_column(Money, default=0)
    packaging: Mapped[Decimal] = mapped_column(Money, default=0)
    inbound_logistics: Mapped[Decimal] = mapped_column(Money, default=0)
    other_variable: Mapped[Decimal] = mapped_column(Money, default=0)
    contribution_profit: Mapped[Decimal] = mapped_column(Money)
    allocated_ad_cost: Mapped[Decimal] = mapped_column(Money, default=0)
    attribution_method: Mapped[str] = mapped_column(String(32))
    attribution_confidence: Mapped[str] = mapped_column(String(8))
    estimated_net_profit: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inputs_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (Index("ix_order_profit_current", "order_id", "is_current"),
                      Index("uq_order_profit_one_current", "order_id", unique=True,
                            postgresql_where=text("is_current")),)


class ReconciliationResult(PKMixin, Base):
    __tablename__ = "analytics_reconciliation"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    run_date: Mapped[date] = mapped_column(Date)
    level: Mapped[str] = mapped_column(String(32))  # order|settlement|payout
    status: Mapped[str] = mapped_column(String(16))  # MATCHED|PARTIAL|MISMATCH|PENDING
    expected_amount: Mapped[Decimal | None] = mapped_column(Money)
    actual_amount: Mapped[Decimal | None] = mapped_column(Money)
    difference: Mapped[Decimal | None] = mapped_column(Money)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DataQualitySnapshot(PKMixin, Base):
    __tablename__ = "analytics_data_quality"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)
    checks: Mapped[dict] = mapped_column(JSONB)


class Recommendation(PKMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    type: Mapped[str] = mapped_column(String(48))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONB)
    confidence: Mapped[str] = mapped_column(String(8))
    estimated_impact: Mapped[dict | None] = mapped_column(JSONB)
    risk: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|accepted|rejected|expired|executed
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[dict | None] = mapped_column(JSONB)  # SPEC §52-53 evaluation


class Alert(PKMixin, Base):
    __tablename__ = "alerts"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    severity: Mapped[str] = mapped_column(String(16))
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str | None] = mapped_column(String(16))


class Task(PKMixin, TimestampMixin, Base):
    """Team action board (SPEC §48, §52)."""
    __tablename__ = "tasks"
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"))
    priority: Mapped[str] = mapped_column(String(4))
    team: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    why: Mapped[str | None] = mapped_column(Text)
    expected_impact: Mapped[dict | None] = mapped_column(JSONB)
    owner: Mapped[str | None] = mapped_column(String(128))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="today")  # today|in_progress|review|done
    source_entity: Mapped[dict | None] = mapped_column(JSONB)
    baseline_metrics: Mapped[dict | None] = mapped_column(JSONB)
    evaluation: Mapped[dict | None] = mapped_column(JSONB)


class AuditLog(PKMixin, Base):
    __tablename__ = "audit_log"
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(96))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

from src.db import models_finance as _models_finance  # noqa: F401  (extends schema)
