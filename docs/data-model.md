# Data Model (Deliverable 2)

Source of truth: `src/db/models.py` (SQLAlchemy 2.0), migrations in `migrations/versions`. PostgreSQL 16.

## Conventions
- Three layers (SPEC §2.2): `raw_api_responses` (verbatim payloads) → normalized tables → `analytics_*`.
- Money: `Numeric(20,6)` + `currency` (ISO-4217) on every money-bearing row. Python side: `Decimal` only. No FX conversion in MVP.
- Time: all instants `timestamptz` in UTC. `metric_date`/`metric_hour` are in the shop's business timezone (`shops.timezone`, Asia/Jakarta). "Today" = shop day.
- Every TikTok entity keeps its external ID with a `UNIQUE(shop_id/parent_id, external_*_id)` → idempotent upserts on re-sync.
- Freshness fields on metric snapshots: `source_updated_at`, `fetched_at`, `is_final` (SPEC §17).
- Nothing is deleted; refunds/adjustments create new rows and a new `analytics_order_profit.version`.

## Entities

### Raw / sync
| Table | Purpose |
|---|---|
| `raw_api_responses` | integration, resource, request_meta, payload (JSONB), fetched_at |
| `integration_sync_state` | per (integration, resource_type, shop) cursor, last_successful_sync, last_attempt, status, error |

### Commerce
| Table | Key fields | Notes |
|---|---|---|
| `shops` | external_shop_id, shop_cipher, currency, timezone, region | one row per authorized shop |
| `shop_config` | thresholds from SPEC §28, operating_mode (MODE_1..4), extra JSONB | 1:1 with shop |
| `products` | external_product_id, title, status, category | |
| `skus` | external_sku_id, seller_sku, variation_data | |
| `sku_cost_versions` | effective_from/to, cogs/packaging/inbound/other per unit, currency | versioned COGS (SPEC §3.4); lookup = latest version with effective_from ≤ order date and (effective_to null or ≥ order date) |
| `creators` | external_creator_id | affiliates |
| `videos` | external_video_id, creator_id, account_type (official/marketing/affiliate/unknown), published_at | |
| `orders` | external_order_id, lifecycle timestamps, order_status, buyer_paid_amount, GMV, discounts, shipping | |
| `order_items` | sku_id, quantity, unit prices, gross_item_value, discounts, creator_id, source_video_id, attribution_source (api/derived/none) | attribution may be derived, never assumed |

### Finance
| Table | Notes |
|---|---|
| `finance_transactions` | native_type preserved + normalized_type (UNKNOWN allowed), amount signed as reported, links to order / item / settlement / payout / raw row |
| `settlements` | period, gross, deductions, net, status |
| `payouts` | amount, status, initiated/completed, bank_reference |

### Metrics (append-only snapshots)
`video_metrics` (date, optional hour), `creator_metrics` (date), `product_metrics` (product/sku, date), `ad_metrics` (entity_type ∈ campaign/adgroup/ad/creative, entity_id, date, optional hour; spend, impressions, clicks, ctr, cpc, cpm, conversions, attributed_orders, attributed_gmv, reported_roas).

### Ads
`ad_accounts` → `campaigns` (campaign_type e.g. GMV_MAX, budget, settings JSONB) → `ad_groups` → `ads` → `ad_creatives` (external_video_id when the API gives it).
`creative_mappings`: creative → video/product/sku with `mapping_source` (api_id / heuristic / manual) and `confidence`. Deterministic ID mapping first; heuristics only as fallback (SPEC §5.15).

### Analytics
| Table | Notes |
|---|---|
| `analytics_order_profit` | every intermediate figure of SPEC §6.2, profit_status (PROVISIONAL/SETTLED/PAID/REFUNDED/ADJUSTED), attribution_method + confidence, `version` + `is_current`, `inputs_snapshot` for audit |
| `analytics_reconciliation` | per order/settlement/payout: status MATCHED/PARTIAL/MISMATCH/PENDING, expected/actual/difference |
| `analytics_data_quality` | periodic snapshot: state, score, checks JSONB |
| `recommendations` | SPEC §13 fields, status open/accepted/rejected/expired/executed, outcome (SPEC §53) |
| `alerts` | severity, dedupe_key, sent_at, channel |
| `tasks` | team action board (SPEC §48/§52): recommendation link, baseline_metrics, evaluation |
| `audit_log` | actor, action, entity, before/after |

## Relationships (ER summary)
```
shops 1─* products 1─* skus 1─* sku_cost_versions
shops 1─* orders 1─* order_items *─1 skus
order_items *─? videos *─? creators
shops 1─* finance_transactions *─? settlements, payouts
videos 1─* video_metrics ; creators 1─* creator_metrics ; products 1─* product_metrics
ad_accounts 1─* campaigns 1─* ad_groups 1─* ads 1─* ad_creatives 1─* creative_mappings *─? videos/products/skus
(entity_type, entity_id) ─ ad_metrics
orders 1─* analytics_order_profit (versions)
recommendations 1─* tasks
```

## Open points (to confirm with real API responses)
- Whether orders carry `source_video_id`/creator natively in ID region → drives `attribution_source`.
- Native finance transaction type vocabulary → `normalized_type` mapping table in `src/analytics/transaction_types.py`.
- Whether ad reports expose creative/video IDs for GMV Max campaigns → `creative_mappings.mapping_source`.
- Hourly granularity availability per metric family.
