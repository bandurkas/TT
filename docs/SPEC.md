# TikTok Shop Profit Control AI Agent

## Technical Specification / Implementation Brief for Claude Code

**Version:** 1.0\
**Date:** 2026-08-30\
**Primary goal:** Build an AI-powered monitoring and decision-support
system for TikTok Shop that connects to TikTok Shop and TikTok Ads APIs,
combines commercial, advertising, content, affiliate, order, settlement,
and internal cost data, and calculates real profit rather than relying
only on platform ROAS.

------------------------------------------------------------------------

# 1. Product Vision

The system must act as an operational AI analyst for a TikTok Shop
business.

It should automatically:

1.  Connect to TikTok Shop API.
2.  Connect to TikTok Ads / Marketing API.
3.  Connect to TikTok Shop Finance / Settlement / Payments data where
    available.
4.  Periodically collect and normalize data.
5.  Link products, SKUs, orders, videos, creators/affiliates, campaigns,
    ad spend, settlements, refunds, fees, and internal COGS.
6.  Calculate real unit economics and net profit.
7.  Detect winning, promising, inefficient, and losing
    videos/campaigns/products.
8.  Detect abnormal changes and likely causes.
9.  Generate short, actionable recommendations in natural language.
10. Send reports and alerts to Telegram and expose a dashboard.
11. Initially operate in **READ → ANALYZE → RECOMMEND** mode.
12. Later support **ASK APPROVAL → EXECUTE** and eventually limited
    automatic optimization.

The main business question is not:

> "What is our TikTok ROAS?"

The main business question is:

> **"Where did we actually make or lose money, why did it happen, and
> what should we do next?"**

------------------------------------------------------------------------

# 2. Core Principles

## 2.1 Profit First

Platform ROAS must not be treated as the primary truth.

Primary metrics:

-   Net Profit
-   Net Margin
-   Contribution Margin
-   Profit per Order
-   Profit per SKU
-   Profit per Product
-   Profit per Video
-   Profit per Creator/Affiliate
-   Profit per Campaign
-   Profit per day/week/month
-   Actual Settlement / Payout
-   Advertising efficiency after all fees and COGS

ROAS remains an important diagnostic metric, but optimization should
ultimately target **real profit**.

## 2.2 Preserve Raw Data

Never overwrite raw API data.

Use three layers:

1.  `raw_*` --- exact API responses / source records.
2.  `normalized_*` --- standardized relational model.
3.  `analytics_*` --- calculated metrics, attribution, classifications,
    alerts and recommendations.

This is necessary because TikTok can change attribution rules, API
fields, fee structures, and reporting logic.

## 2.3 Explain Every Recommendation

The AI must never output only:

> "Stop video X."

It should explain:

-   what changed;
-   compared with what period;
-   which metrics caused the conclusion;
-   confidence level;
-   expected benefit/risk;
-   which data may still be incomplete.

## 2.4 No Autonomous Spend Changes in MVP

MVP must be read-only regarding advertising changes.

No campaign/budget/bid modification without an explicit later feature
flag and approval workflow.

------------------------------------------------------------------------

# 3. External Integrations

Implementation must verify the latest official TikTok API documentation
before coding because endpoints, permissions, versions, field names and
regional availability may change.

## 3.1 TikTok Shop API

Required categories where supported:

-   Shop analytics
-   Orders
-   Products
-   SKUs
-   Video performance
-   Video-product performance
-   LIVE performance
-   Affiliate / creator performance
-   Shop performance
-   Product performance
-   Refund/return information
-   Finance / statements / settlements
-   Payments / payouts

Important official documentation areas previously identified:

-   TikTok Shop Developer Guide
-   Shop Video Performance
-   Shop Video Performance Overview
-   Shop Product Performance Detail
-   Accounting and Finance
-   Finance API
-   Payments API

Do not hardcode endpoint assumptions from this document. Build an
adapter around the current official API.

## 3.2 TikTok Ads / Marketing API

Collect where available:

-   advertiser account;
-   campaign;
-   ad group;
-   ad;
-   creative/video ID;
-   spend;
-   impressions;
-   reach;
-   clicks;
-   CTR;
-   CPC;
-   CPM;
-   conversions;
-   attributed orders;
-   attributed GMV;
-   reported ROAS;
-   GMV Max reporting;
-   campaign/ad status;
-   budget;
-   optimization settings;
-   reporting dimensions and timestamps.

## 3.3 Telegram Bot

Telegram should provide:

-   daily summary;
-   anomaly alerts;
-   winning-video alerts;
-   losing-spend alerts;
-   profit alerts;
-   optional interactive approval buttons in future versions.

Environment variables:

``` env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## 3.4 Internal Cost Data

TikTok does not know all internal costs.

Create internal configuration/database for:

-   SKU COGS;
-   packaging cost;
-   inbound logistics allocation;
-   optional warehouse/fulfillment cost;
-   optional fixed cost allocation;
-   optional taxes not included in TikTok settlement;
-   other user-defined variable costs.

COGS must be versioned by effective date.

Example:

``` text
SKU: LOMIRA-WHITE-5
Effective from: 2026-08-01
COGS/unit: 25,000 IDR
Packaging/unit: 1,500 IDR
Inbound logistics/unit: 700 IDR
```

Historical orders must use the cost version effective at the order date.

------------------------------------------------------------------------

# 4. Authentication and Security

Requirements:

-   OAuth/token handling according to official TikTok requirements.
-   Refresh tokens automatically where supported.
-   Encrypt secrets at rest.
-   Never expose tokens in logs.
-   Separate development and production credentials.
-   `.env` only for local development.
-   Production secrets through a proper secret manager.
-   Store API permission scopes.
-   Log authentication failures without secret values.
-   Support reconnect/re-authorization flow.
-   All write-capable API permissions should be excluded from MVP unless
    absolutely required.

------------------------------------------------------------------------

# 5. Data Model

Recommended database: PostgreSQL.

Use migrations.

Minimum entities follow.

## 5.1 Shops

``` text
shops
- id
- platform
- external_shop_id
- name
- currency
- timezone
- region
- status
- created_at
- updated_at
```

## 5.2 Products

``` text
products
- id
- shop_id
- external_product_id
- title
- status
- category
- created_at
- updated_at
```

## 5.3 SKUs

``` text
skus
- id
- product_id
- external_sku_id
- seller_sku
- title
- variation_data
- status
```

## 5.4 SKU Cost Versions

``` text
sku_cost_versions
- id
- sku_id
- effective_from
- effective_to
- cogs_per_unit
- packaging_per_unit
- inbound_logistics_per_unit
- other_variable_cost_per_unit
- currency
- notes
```

## 5.5 Orders

``` text
orders
- id
- shop_id
- external_order_id
- order_created_at
- paid_at
- shipped_at
- completed_at
- cancelled_at
- order_status
- buyer_paid_amount
- gross_merchandise_value
- seller_discount
- platform_discount
- shipping_amount
- currency
- raw_source_updated_at
```

## 5.6 Order Items

``` text
order_items
- id
- order_id
- product_id
- sku_id
- quantity
- unit_list_price
- unit_sale_price
- gross_item_value
- discounts
- creator_id nullable
- source_video_id nullable
```

Do not assume source video or creator is directly available on every
order. Attribution may require derived matching.

## 5.7 Finance Transactions

``` text
finance_transactions
- id
- shop_id
- external_transaction_id
- external_order_id nullable
- order_item_id nullable
- transaction_type
- amount
- currency
- transaction_at
- settlement_id nullable
- payout_id nullable
- status
- raw_payload_reference
```

Transaction types should preserve TikTok's native categories and
optionally map to internal normalized categories:

-   sale proceeds
-   platform commission
-   affiliate commission
-   shipping fee
-   shipping adjustment
-   tax
-   refund
-   refund fee adjustment
-   seller discount
-   platform subsidy
-   service fee
-   transaction fee
-   other adjustment

Do not force unknown transactions into an existing category. Store
`UNKNOWN` plus native type.

## 5.8 Settlements

``` text
settlements
- id
- shop_id
- external_settlement_id
- period_start
- period_end
- gross_amount
- deductions
- net_amount
- currency
- status
- settlement_at
```

## 5.9 Payouts

``` text
payouts
- id
- shop_id
- external_payout_id
- payout_amount
- currency
- payout_status
- initiated_at
- completed_at
- bank_reference nullable
```

## 5.10 Videos

``` text
videos
- id
- shop_id
- external_video_id
- creator_id nullable
- account_type
- published_at
- duration
- caption
- status
- video_url_or_reference nullable
```

Account/source types may include where supported:

-   official
-   marketing
-   affiliate
-   unknown

## 5.11 Video Metrics

Use time-series snapshots.

``` text
video_metrics
- id
- video_id
- metric_date
- metric_hour nullable
- views
- impressions nullable
- product_clicks
- ctr
- orders
- units_sold
- gmv
- gpm
- conversion_rate
- likes nullable
- comments nullable
- shares nullable
```

## 5.12 Creators / Affiliates

``` text
creators
- id
- shop_id
- external_creator_id
- display_name
- account_name
- status
```

``` text
creator_metrics
- creator_id
- metric_date
- videos_count
- views
- clicks
- orders
- units
- gmv
- commission
- estimated_profit
```

## 5.13 Ads Hierarchy

``` text
ad_accounts
campaigns
ad_groups
ads
ad_creatives
```

Each table should preserve TikTok external IDs.

## 5.14 Ad Metrics

``` text
ad_metrics
- entity_type
- entity_id
- metric_date
- metric_hour nullable
- spend
- impressions
- clicks
- ctr
- cpc
- cpm
- conversions
- attributed_orders
- attributed_gmv
- reported_roas
```

## 5.15 Creative Mapping

A critical table:

``` text
creative_mappings
- ad_creative_id
- video_id nullable
- product_id nullable
- sku_id nullable
- mapping_source
- confidence
```

Need deterministic mapping when TikTok provides IDs; AI/heuristic
mapping only as fallback.

------------------------------------------------------------------------

# 6. Financial Calculation Engine

This module is business-critical and should be deterministic code, not
an LLM calculation.

## 6.1 Revenue Levels

Keep separate:

1.  Listed product value.
2.  Buyer paid value.
3.  GMV as defined by TikTok.
4.  Estimated seller proceeds.
5.  Final settlement.
6.  Actual payout.

Never mix these concepts.

## 6.2 Order-Level Profit

Conceptual calculation:

``` text
Net Seller Revenue
= Sale proceeds
- Seller-funded discounts
- Platform/service fees charged to seller
- Affiliate commission
- Seller-borne shipping
- Taxes charged to seller
- Refunds
+ Platform subsidies/credits
+/- Adjustments
```

Then:

``` text
Contribution Profit Before Ads
= Net Seller Revenue
- COGS
- Packaging
- Inbound Logistics
- Other Variable Internal Costs
```

Then:

``` text
Estimated Net Profit
= Contribution Profit Before Ads
- Allocated Advertising Cost
```

The exact treatment of every TikTok finance transaction must be
configured from actual API transaction semantics.

## 6.3 Profit Status

Every calculated order/profit record must have a state:

``` text
PROVISIONAL
SETTLED
PAID
REFUNDED
ADJUSTED
```

Example:

-   `PROVISIONAL`: order completed but final finance data incomplete.
-   `SETTLED`: final settlement available.
-   `PAID`: payout confirmed.
-   `REFUNDED`: order fully refunded.
-   `ADJUSTED`: post-settlement adjustment occurred.

## 6.4 Advertising Cost Allocation

This is not always deterministic.

Support several attribution models:

### A. Platform Reported

Use TikTok-reported attribution.

### B. Direct Creative Attribution

If ad/video/order relationship is explicitly provided.

### C. Proportional Allocation

Allocate spend based on attributed GMV/orders when exact order-level
mapping is unavailable.

### D. Blended

For shop-level profitability:

``` text
Blended Marketing Cost Ratio = Total Ad Spend / Net Revenue
```

Always save:

``` text
attribution_method
attribution_confidence
```

Never present estimated order-level ad cost as exact.

------------------------------------------------------------------------

# 7. GMV Max Attribution Warning

This is a mandatory design requirement.

TikTok's GMV Max reporting/attribution can differ from a simplistic
"this ad directly generated this sale" interpretation.

Therefore maintain at least:

``` text
reported_gmv
reported_roas
direct_or_supported_attributed_gmv
organic_gmv
blended_gmv
adjusted_roas
```

Do not claim "incremental ROAS" unless the methodology actually supports
causal incrementality.

Use wording such as:

-   Reported ROAS
-   Adjusted ROAS
-   Blended ROAS
-   Attributed ROAS

Every dashboard/report must clearly label which one is being shown.

------------------------------------------------------------------------

# 8. Analytics Engine

Analytics must work independently of the LLM.

## 8.1 Baselines

Calculate rolling baselines:

-   last 24 hours;
-   previous comparable 24 hours;
-   3-day average;
-   7-day average;
-   14-day average;
-   30-day average;
-   same weekday baseline where useful.

## 8.2 Core KPIs

Shop:

-   GMV
-   Net Revenue
-   Orders
-   Units
-   AOV
-   refunds
-   refund rate
-   TikTok fees
-   affiliate fees
-   ad spend
-   reported ROAS
-   adjusted/blended ROAS
-   COGS
-   contribution profit
-   net profit
-   net margin

Product/SKU:

-   views
-   clicks
-   CTR
-   CVR
-   units
-   GMV
-   net revenue
-   profit
-   margin
-   refund rate
-   ad spend allocation

Video:

-   views
-   product clicks
-   CTR
-   CVR
-   orders
-   units
-   GMV
-   ad spend
-   reported ROAS
-   estimated/settled profit
-   profit per 1,000 views
-   GMV per 1,000 views
-   profit per click
-   age of creative
-   trend

Creator:

-   videos
-   GMV
-   orders
-   affiliate commission
-   profit after affiliate commission
-   profit per video

## 8.3 Funnel

For each video/product where data allows:

``` text
Impression/View
    ↓
Product Click
    ↓
Add to Cart (if available)
    ↓
Checkout (if available)
    ↓
Order
    ↓
Paid
    ↓
Completed
    ↓
Settled
    ↓
Paid Out
```

The system should identify the stage with the largest deterioration.

------------------------------------------------------------------------

# 9. Creative Classification

Do not use fixed universal thresholds only.

Thresholds should primarily compare each video against:

-   account median;
-   product median;
-   category/product group;
-   recent 7/14/30-day baseline;
-   minimum sample requirements.

Classification:

## 9.1 WINNER / SCALE CANDIDATE

Typical signals:

-   enough sample size;
-   CTR above baseline;
-   CVR healthy;
-   profitable after fees/COGS/ad cost;
-   positive recent trend;
-   no abnormal refund rate.

Output example:

``` text
🔥 WINNER
Video: 184
Orders: 37
Net Profit: Rp 615,000
Net Margin: 22.4%
CTR: +41% vs 7-day video median
CVR: +28% vs product median
Confidence: HIGH
Recommendation: Produce 3-5 variants and consider additional traffic.
```

## 9.2 PROMISING

Signals:

-   small sample;
-   strong CTR or early CVR;
-   insufficient spend/orders for certainty.

Never recommend aggressive scaling.

## 9.3 TRAFFIC_NO_SALES

Signals:

-   strong traffic/CTR;
-   weak purchase conversion.

Investigate:

-   price;
-   voucher;
-   shipping;
-   product page;
-   stock/variant availability;
-   rating/reviews if accessible;
-   product mismatch;
-   offer;
-   recent conversion change.

## 9.4 LOW_ATTENTION

Signals:

-   weak CTR / low product-click rate;
-   enough impressions/views.

Likely creative/hook issue.

## 9.5 LOSER / STOP CANDIDATE

Signals:

-   sufficient spend/sample;
-   low conversion;
-   negative contribution after ads;
-   performance significantly below baseline.

Recommendation must include potential daily saving.

## 9.6 FATIGUING

Detect creative fatigue:

-   falling CTR;
-   rising CPC/CPM;
-   falling CVR;
-   increasing frequency if available;
-   performance decay over multiple days.

------------------------------------------------------------------------

# 10. Root-Cause Analysis

The system must not stop at anomaly detection.

Example event:

``` text
Adjusted ROAS: 4.7 → 2.9
```

Root-cause engine should test possible contributors:

1.  Spend increased.
2.  CPM increased.
3.  CTR decreased.
4.  CPC increased.
5.  Product conversion decreased.
6.  AOV decreased.
7.  Product price changed.
8.  Voucher disappeared/changed.
9.  Stock/variant became unavailable.
10. Refund rate increased.
11. Affiliate commission changed.
12. TikTok fees changed.
13. One creative absorbed excessive spend.
14. Winning creative lost delivery.
15. Product mix shifted.
16. Attribution/reporting lag.
17. Settlement data is incomplete.

Rank causes by quantified contribution where possible.

Example:

``` text
ROAS decline explanation

Estimated contribution:
- Video #72 spend expansion: 48%
- Product CVR decline: 31%
- CPM increase: 14%
- Other/unknown: 7%

Confidence: MEDIUM
```

------------------------------------------------------------------------

# 11. AI Agent Architecture

Use deterministic analytics first, LLM second.

LLM must interpret structured analytics output rather than calculate raw
metrics itself.

## Agent 1 --- Performance Analyst

Responsibilities:

-   shop health;
-   day-over-day/week-over-week changes;
-   campaign performance;
-   major anomalies;
-   summarize causes.

## Agent 2 --- Creative Analyst

Responsibilities:

-   classify videos;
-   detect winners;
-   detect fatigue;
-   compare paid vs organic vs affiliate content;
-   identify high-CTR/low-CVR content.

## Agent 3 --- Product Analyst

Responsibilities:

-   SKU/product profitability;
-   conversion changes;
-   stock/variant issues;
-   price/voucher effects where data exists;
-   refund problems.

## Agent 4 --- Profit Analyst

Responsibilities:

-   settlements;
-   fees;
-   COGS;
-   affiliate costs;
-   ad allocation;
-   profit/margin;
-   reconciliation between estimated, settled and paid values.

## Agent 5 --- Creative Strategist

Input:

-   top-performing videos;
-   bottom-performing videos;
-   video metadata/transcripts/vision analysis where legally and
    technically available.

Output:

-   recurring winning patterns;
-   hook ideas;
-   offer patterns;
-   CTA patterns;
-   suggested new variations;
-   briefs for content team.

Important: performance correlation must not automatically be described
as causal.

## Agent 6 --- Ads Operator (Future)

Not active in MVP.

Future permissions:

-   pause ad;
-   change budget;
-   adjust target;
-   activate creative.

Requires:

-   explicit approval;
-   hard limits;
-   audit log;
-   rollback strategy;
-   maximum daily change rules.

------------------------------------------------------------------------

# 12. LLM Output Contract

LLM should receive structured JSON similar to:

``` json
{
  "period": {},
  "shop_summary": {},
  "changes": [],
  "anomalies": [],
  "video_rankings": [],
  "product_rankings": [],
  "profit_summary": {},
  "settlement_status": {},
  "data_quality": {},
  "candidate_actions": []
}
```

LLM returns:

``` json
{
  "summary": "...",
  "important_changes": [],
  "root_causes": [],
  "recommended_actions": [],
  "risks": [],
  "data_caveats": []
}
```

Validate output against JSON schema.

Never allow free-form LLM output to directly trigger API write
operations.

------------------------------------------------------------------------

# 13. Recommendation Engine

Every recommendation should contain:

``` text
type
entity_type
entity_id
title
reason
evidence
confidence
estimated_impact
risk
recommended_action
requires_approval
created_at
expires_at
```

Example:

``` text
Title:
Reduce spend on Video #162

Evidence:
- Rp 143,000 spend
- 0 orders
- CTR 0.8% vs account median 2.3%
- 8,200 impressions
- no product conversion
- performance below threshold for 18 hours

Estimated impact:
Potential saving ~Rp 143,000/day if current run rate continues.

Confidence:
HIGH
```

------------------------------------------------------------------------

# 14. Alerts

Alert only when useful. Avoid notification spam.

Severity:

``` text
INFO
OPPORTUNITY
WARNING
CRITICAL
```

Examples:

### OPPORTUNITY

Winning video detected.

### WARNING

Spend increasing without proportional orders.

### CRITICAL

Large spend with zero/negative profit.

### CRITICAL

Shop net margin falls below configured floor.

### WARNING

Settlement mismatch.

### WARNING

API data has stopped updating.

Deduplicate repeated alerts.

Implement cooldowns.

------------------------------------------------------------------------

# 15. Telegram Reports

## 15.1 Daily Report Example

``` text
TikTok Shop — Daily Profit Report

GMV: Rp 4.8m
Net Seller Revenue: Rp 3.92m
Ad Spend: Rp 820k
COGS: Rp 1.60m
Affiliate/Platform/Other Fees: Rp 610k

Estimated Net Profit: Rp 890k
Net Margin: 18.5%

Reported ROAS: 5.85
Adjusted/Blended ROAS: 4.78

🔥 Winner
Video #184
37 orders
Estimated profit: Rp 615k
CTR +41% vs 7-day median

⚠️ Losing Spend
Video #162
Spend Rp 143k
0 orders

Recommendation:
Reduce exposure to #162 and create 3 variants of #184.

Data status:
92% settled / 8% provisional
```

Numbers above are illustrative only.

## 15.2 Immediate Alert

``` text
⚠️ TikTok Shop Alert

Product: LOMIRA White 5
Conversion fell 4.8% → 2.7%

Traffic is stable.
CTR is stable.
Main deterioration occurs after product click.

Possible causes:
1. Voucher/price change
2. Stock/variant availability
3. Product page conversion issue

Confidence: MEDIUM
```

------------------------------------------------------------------------

# 16. Dashboard

MVP dashboard sections:

## Overview

-   GMV
-   Net Revenue
-   Orders
-   Ad Spend
-   Reported ROAS
-   Adjusted/Blended ROAS
-   COGS
-   Net Profit
-   Net Margin
-   Settlement coverage

## Videos

Table:

``` text
Video
Source
Age
Views
Clicks
CTR
Orders
CVR
GMV
Ad Spend
Profit
Margin
Classification
Trend
```

Filters:

-   date;
-   product;
-   SKU;
-   source/account type;
-   affiliate;
-   classification;
-   paid/organic where determinable.

## Products

``` text
Product/SKU
Units
GMV
Net Revenue
Fees
COGS
Ads
Profit
Margin
Refund Rate
```

## Ads

Campaign → Ad Group → Ad → Creative drilldown.

## Finance

-   provisional proceeds;
-   settlements;
-   payouts;
-   refunds;
-   adjustments;
-   reconciliation;
-   settlement vs internal profit.

## Recommendations

Show:

-   open;
-   accepted;
-   rejected;
-   expired;
-   executed (future).

------------------------------------------------------------------------

# 17. Data Freshness and Scheduling

Suggested MVP schedule, subject to API rate limits:

### Every 1 hour

-   ad performance;
-   shop performance;
-   video performance;
-   product performance;
-   order updates.

### Every 3--6 hours

-   finance/settlement updates;
-   affiliate updates;
-   deeper anomaly analysis.

### Daily

-   full reconciliation;
-   daily report;
-   historical backfill check;
-   recompute changed/refunded orders.

Never assume data is final immediately.

Track:

``` text
source_updated_at
fetched_at
is_final
data_latency_minutes
```

------------------------------------------------------------------------

# 18. Data Quality Layer

Before producing recommendations, calculate data-quality state.

Checks:

-   API freshness;
-   missing hours;
-   missing orders;
-   duplicate transactions;
-   unmapped SKU;
-   unmapped creative;
-   missing COGS;
-   missing settlement;
-   currency mismatch;
-   attribution uncertainty;
-   unexpected negative values;
-   TikTok API/reporting lag.

Example:

``` text
DATA QUALITY: PARTIAL

Reason:
18% of today's orders do not yet have final settlement data.

Profit shown as estimated.
```

If critical data is incomplete, AI must downgrade confidence.

------------------------------------------------------------------------

# 19. Reconciliation

This is mandatory.

Daily reconciliation should compare:

``` text
Orders
↕
Order Items
↕
Finance Transactions
↕
Settlements
↕
Payouts
```

Create reconciliation status:

``` text
MATCHED
PARTIAL
MISMATCH
PENDING
```

Store difference amount.

Do not silently hide discrepancies.

------------------------------------------------------------------------

# 20. Refunds and Returns

Profit must be recalculated when:

-   order cancelled;
-   partial refund;
-   full refund;
-   return;
-   settlement adjustment;
-   affiliate adjustment;
-   shipping adjustment.

Historical profit is therefore mutable.

Keep calculation versions/audit history.

------------------------------------------------------------------------

# 21. Multi-Currency

Initial target may be IDR, but architecture should support currencies.

Store money as:

-   integer minor units when appropriate, or
-   high-precision decimal.

Never use floating point for financial calculations.

Store:

``` text
amount
currency
```

Do not convert currencies unless required.

If conversion is added, preserve original amount and FX
source/rate/date.

------------------------------------------------------------------------

# 22. Time Zones

Use shop timezone for business reporting.

Store timestamps in UTC internally where practical, plus shop timezone
configuration.

"Today" must mean the TikTok Shop business day, not server UTC day.

------------------------------------------------------------------------

# 23. Suggested Technical Stack

Claude Code may adapt this, but recommended:

### Backend

-   Python 3.12+
-   FastAPI
-   Pydantic
-   SQLAlchemy
-   Alembic

### Database

-   PostgreSQL

### Jobs

Start simple:

-   Celery + Redis, or
-   APScheduler for very small MVP.

Prefer Celery/Redis if multiple shops/accounts are expected.

### AI

Provider abstraction:

``` text
LLMProvider
- analyze_performance()
- explain_anomaly()
- generate_daily_report()
- generate_creative_brief()
```

Do not tightly couple the system to one LLM vendor.

### Frontend

-   Next.js
-   TypeScript
-   simple responsive admin dashboard

### Infrastructure

-   Docker / Docker Compose
-   structured logging
-   Sentry-compatible error tracking
-   environment-based config

------------------------------------------------------------------------

# 24. Suggested Repository Structure

``` text
tiktok-profit-agent/
│
├── apps/
│   ├── api/
│   ├── worker/
│   └── dashboard/
│
├── src/
│   ├── integrations/
│   │   ├── tiktok_shop/
│   │   ├── tiktok_ads/
│   │   └── telegram/
│   │
│   ├── domain/
│   │   ├── orders/
│   │   ├── products/
│   │   ├── finance/
│   │   ├── ads/
│   │   ├── videos/
│   │   └── creators/
│   │
│   ├── analytics/
│   │   ├── profitability.py
│   │   ├── attribution.py
│   │   ├── baselines.py
│   │   ├── creative_scoring.py
│   │   ├── anomaly_detection.py
│   │   ├── root_cause.py
│   │   └── reconciliation.py
│   │
│   ├── agents/
│   │   ├── performance_agent.py
│   │   ├── creative_agent.py
│   │   ├── product_agent.py
│   │   ├── profit_agent.py
│   │   └── strategist_agent.py
│   │
│   ├── recommendations/
│   ├── alerts/
│   ├── reports/
│   ├── db/
│   └── config/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── migrations/
├── docker-compose.yml
├── .env.example
└── README.md
```

------------------------------------------------------------------------

# 25. API Adapter Requirements

All TikTok integrations must be isolated behind adapters.

Example interface:

``` python
class TikTokShopClient:
    def get_orders(...): ...
    def get_products(...): ...
    def get_video_performance(...): ...
    def get_product_performance(...): ...
    def get_finance_transactions(...): ...
    def get_settlements(...): ...
    def get_payouts(...): ...
```

Ads:

``` python
class TikTokAdsClient:
    def get_campaigns(...): ...
    def get_ads(...): ...
    def get_creatives(...): ...
    def get_report(...): ...
    def get_gmv_max_report(...): ...
```

Benefits:

-   API versions can change without rewriting business logic.
-   easy mocking/testing;
-   easy addition of another marketplace later.

------------------------------------------------------------------------

# 26. Sync Requirements

Every synchronization job must be:

-   idempotent;
-   retryable;
-   observable;
-   paginated;
-   rate-limit aware;
-   capable of incremental sync;
-   capable of historical backfill.

Store sync state:

``` text
integration_sync_state
- integration
- resource_type
- shop_id
- cursor
- last_successful_sync
- last_attempt
- status
- error
```

Use exponential backoff.

Never duplicate transactions/orders on retries.

------------------------------------------------------------------------

# 27. Audit Log

Track:

-   API syncs;
-   cost changes;
-   configuration changes;
-   recommendation generation;
-   user approval/rejection;
-   future ad changes.

Example:

``` text
audit_log
- actor
- action
- entity_type
- entity_id
- before
- after
- timestamp
```

------------------------------------------------------------------------

# 28. Configuration

Per shop:

``` text
minimum_net_margin
minimum_profit_per_order
max_acceptable_cpa
minimum_sample_impressions
minimum_sample_clicks
minimum_sample_orders
alert_cooldown
timezone
currency
report_time
```

Avoid hardcoding business thresholds.

------------------------------------------------------------------------

# 29. Creative Intelligence --- Phase 2

Once base analytics works, add actual video-content understanding.

Pipeline:

``` text
Video
↓
Metadata
↓
Transcript / captions
↓
Key frames / vision analysis
↓
Creative features
↓
Performance data
↓
Pattern analysis
```

Extract features:

-   first 1--3 second hook;
-   person/no person;
-   product appears immediately/later;
-   problem/solution;
-   demonstration;
-   testimonial;
-   price shown;
-   discount/voucher shown;
-   CTA;
-   video duration;
-   text density;
-   spoken language;
-   UGC vs studio;
-   creator type.

Then correlate with:

-   CTR;
-   CVR;
-   GMV;
-   profit;
-   retention metrics if accessible.

Example result:

``` text
Winning pattern detected

4 of top 5 profitable videos:
- show product in first 2 seconds
- demonstrate a problem
- mention pack quantity
- CTA appears before second 15

Recommendation:
Produce 5 controlled variations of this structure.
```

Again: label this as observed association unless a controlled experiment
supports causality.

------------------------------------------------------------------------

# 30. Experiment Framework --- Phase 2

Allow creative tests.

``` text
Experiment
Hypothesis
Control
Variants
Start date
End date
Primary KPI
Guardrail KPI
Result
Confidence
```

Recommended primary KPI:

**Profit per 1,000 qualified impressions/views** or another profit-based
metric depending on available attribution.

Guardrails:

-   refund rate;
-   net margin;
-   CPA;
-   sample size.

------------------------------------------------------------------------

# 31. Future Automatic Optimization

Only after recommendation accuracy is validated.

Modes:

``` text
MODE_1 = READ_ONLY
MODE_2 = RECOMMEND
MODE_3 = APPROVAL_REQUIRED
MODE_4 = LIMITED_AUTOMATION
```

Default:

``` text
MODE_2
```

Example safety limits for future configuration:

``` text
max_budget_change_percent = 10
max_extra_spend_per_day = 200000 IDR
max_actions_per_day = 5
require_approval_for_pause = true
require_approval_above_amount = ...
```

Never allow the LLM to bypass limits.

Execution flow:

``` text
Analytics
↓
Recommendation
↓
Policy Engine
↓
Human Approval
↓
TikTok Ads API
↓
Verification
↓
Audit Log
```

------------------------------------------------------------------------

# 32. MVP Scope

## Must Have

1.  TikTok Shop authorization.
2.  TikTok Ads authorization.
3.  Shop/product/SKU synchronization.
4.  Order synchronization.
5.  Video performance synchronization.
6.  Advertising reporting.
7.  Finance/settlement data where API access permits.
8.  Internal SKU COGS management.
9.  Profit calculation engine.
10. Video classification.
11. Basic anomaly detection.
12. Daily Telegram report.
13. Critical alerts.
14. Dashboard.
15. Data-quality indicator.
16. Reconciliation.
17. Audit log.

## Not Required for MVP

-   autonomous budget changes;
-   automatic campaign creation;
-   sophisticated video vision analysis;
-   multi-marketplace support;
-   predictive ML models;
-   mobile application.

------------------------------------------------------------------------

# 33. MVP Success Criteria

MVP is successful if for a selected reporting period the user can
answer:

### Business

-   How much GMV did we generate?
-   How much money did TikTok actually settle/pay?
-   How much did TikTok deduct?
-   How much was affiliate commission?
-   How much did we spend on ads?
-   What was COGS?
-   What was estimated/final net profit?
-   What was net margin?

### Product

-   Which SKU made the most profit?
-   Which SKU lost money?
-   Which SKU has declining conversion?

### Content

-   Which videos generated the most orders?
-   Which videos generated the most profit?
-   Which videos consume spend without sales?
-   Which videos are promising but under-tested?
-   Which affiliate creators generate profitable sales?

### Decision

-   What should be scaled?
-   What should be reduced/stopped?
-   What needs new creative?
-   What product-page/offer issue needs investigation?
-   How confident is the system?

------------------------------------------------------------------------

# 34. Testing Requirements

High test coverage for all financial logic.

Mandatory unit tests:

-   COGS calculation;
-   partial refund;
-   full refund;
-   affiliate commission;
-   TikTok fee;
-   platform subsidy;
-   seller discount;
-   settlement adjustment;
-   ad cost allocation;
-   multiple SKUs per order;
-   historical COGS version;
-   missing settlement;
-   duplicate finance transaction;
-   negative adjustment;
-   currency precision.

Use fixed fixtures.

Example:

``` text
Order sale proceeds: 75,000
Fees: 8,000
Affiliate: 5,000
COGS: 25,000
Packaging: 1,500
Allocated ads: 12,000

Expected profit:
23,500
```

The test should assert exact decimal/integer result.

------------------------------------------------------------------------

# 35. Observability

Track:

-   sync success rate;
-   API latency;
-   API errors;
-   rate limits;
-   number of records fetched;
-   last fresh timestamp;
-   analytics duration;
-   AI request failures;
-   Telegram delivery failures;
-   reconciliation mismatches.

Expose `/health` and `/ready`.

------------------------------------------------------------------------

# 36. Privacy and Data Retention

Do not collect buyer PII unless technically necessary.

Prefer IDs and aggregated commercial metrics.

If buyer data is returned:

-   minimize storage;
-   encrypt sensitive fields;
-   define retention;
-   never send unnecessary buyer PII to an LLM.

------------------------------------------------------------------------

# 37. Development Plan

## Phase 0 --- API Validation

Before building the application:

1.  Register/verify TikTok developer access.
2.  Confirm available Shop scopes for target account/region.
3.  Confirm Ads API access.
4.  Confirm Finance/Settlement/Payments access.
5.  Confirm video-level analytics fields.
6.  Confirm affiliate fields.
7.  Confirm GMV Max reporting availability.
8.  Document actual endpoint versions and response examples.

Deliver:

``` text
docs/tiktok-api-capability-matrix.md
```

This must clearly mark:

``` text
AVAILABLE
NOT AVAILABLE
REQUIRES APPROVAL
REGION LIMITED
UNKNOWN
```

## Phase 1 --- Data Foundation

Build:

-   PostgreSQL;
-   migrations;
-   OAuth;
-   API clients;
-   raw ingestion;
-   normalized models;
-   incremental sync.

## Phase 2 --- Finance Engine

Build:

-   COGS;
-   transaction normalization;
-   settlement;
-   payout;
-   refunds;
-   profit;
-   reconciliation.

Validate manually against several real TikTok orders.

**Do not continue to automated recommendations until financial
calculations are verified against the Seller Center.**

## Phase 3 --- Ads + Creative Analytics

Build:

-   ads reports;
-   video metrics;
-   creative mappings;
-   baselines;
-   classifications;
-   anomaly detection.

## Phase 4 --- AI Layer

Build agents only after analytics outputs are reliable.

LLM receives calculated facts and generates:

-   explanation;
-   priorities;
-   recommendations;
-   creative briefs.

## Phase 5 --- Telegram + Dashboard

Deliver daily reports, alerts and UI.

## Phase 6 --- Validation

Run in shadow mode for at least 2--4 weeks.

Compare AI recommendations with actual outcomes.

Track recommendation quality.

Only then consider write permissions.

------------------------------------------------------------------------

# 38. Critical Rules for Claude Code

1.  **Do not invent TikTok API endpoints.**
2.  Verify current official TikTok documentation before implementing
    each adapter.
3.  If an API field is unavailable, mark the feature as unavailable
    rather than fabricate a workaround.
4.  Keep all financial calculations deterministic.
5.  Use `Decimal` / integer minor units, never float.
6.  LLM must not be the source of truth for numbers.
7.  Preserve raw TikTok responses.
8.  Make ingestion idempotent.
9.  Never treat provisional settlement as final.
10. Never present estimated ad attribution as exact.
11. Clearly separate TikTok-reported ROAS from internal adjusted/blended
    metrics.
12. Do not automatically modify ads in MVP.
13. Every recommendation needs evidence and confidence.
14. Missing/late data must lower recommendation confidence.
15. Every future write operation requires policy checks and audit
    logging.
16. Build API adapters so TikTok version changes are isolated.
17. Prioritize financial correctness over UI polish.

------------------------------------------------------------------------

# 39. First Deliverables Requested from Claude Code

Before writing the full product, produce:

### Deliverable 1

`docs/tiktok-api-capability-matrix.md`

Map each required data point to the current official TikTok API:

``` text
Data Point | API | Endpoint | Scope | Granularity | Freshness | Available? | Notes
```

### Deliverable 2

`docs/data-model.md`

Final ER model and relationships.

### Deliverable 3

`docs/profit-calculation.md`

Exact financial formulas and mapping of every TikTok finance transaction
type.

### Deliverable 4

`docs/attribution-model.md`

Explain:

-   TikTok reported attribution;
-   GMV Max attribution;
-   internal adjusted attribution;
-   ad cost allocation;
-   confidence levels.

### Deliverable 5

Working API connectivity test.

It should fetch and save a small sample of:

-   shop;
-   products/SKUs;
-   orders;
-   videos;
-   ad report;
-   finance data.

### Deliverable 6

Reconciliation test against manually selected real orders.

Only after these six deliverables are accepted should Claude Code
proceed with the complete MVP.

------------------------------------------------------------------------

# 40. Final Product Definition

The final system is best described as:

> **TikTok Shop Profit Control AI**

It is not simply an advertising dashboard.

Its job is to connect:

``` text
CONTENT
   ↓
VIDEO / CREATOR
   ↓
ADVERTISING
   ↓
PRODUCT / SKU
   ↓
ORDER
   ↓
FINANCE / SETTLEMENT
   ↓
COGS
   ↓
REAL PROFIT
   ↓
AI RECOMMENDATION
```

The system should ultimately tell the operator:

1.  **What made money?**
2.  **What lost money?**
3.  **Why?**
4.  **Which video/product/creator/campaign caused it?**
5.  **What should we do now?**
6.  **How much money could that action save or earn?**
7.  **How confident are we in that recommendation?**

That is the core product requirement.
---

# 41. Sales & Creative Command Center Dashboard

The product must include a dedicated operational dashboard. Telegram messages are only alerts and summaries. The dashboard is the primary daily working surface for management, marketing, design, videography/content, and performance teams.

The dashboard must answer within roughly 30 seconds:

1. Are sales and real profit healthy today?
2. Where exactly is performance dropping?
3. Why is it dropping?
4. Which campaign, product, SKU, video, creator, or funnel stage is responsible?
5. What are the biggest opportunities right now?
6. What should each team do today?

## 41.1 Dashboard Design Principles

Use the best patterns from modern analytics and workspace products:

- **At-a-glance first, drill-down second.** Start with a small number of critical KPIs and allow every card to open the underlying detail.
- **Global filters.** One filter bar must control all relevant widgets.
- **Comparison is mandatory.** Every important KPI should show change vs previous comparable period or selected baseline.
- **Insights before raw tables.** Surface meaningful changes, anomalies and actions before detailed data.
- **Stable app-like layout.** Users should not need to rearrange the page to use it every day.
- **Progressive disclosure.** Keep the first screen simple; detailed tables and diagnostics appear on drill-down.
- **Action-oriented UI.** Every important anomaly should connect to a cause and recommended next action.
- **Do not overload the dashboard.** Prefer focused cards and drill-down pages instead of giant unfiltered tables.
- **Role-aware views.** Management, Performance Marketing, Creative/Video, and Product teams can use different default views over the same data.
- **Desktop-first but fully responsive for tablet/mobile.**

Reference patterns to emulate conceptually:
- Notion: stable dashboard layout, widgets, multiple views of the same underlying data, global filters, focused widgets.
- Shopify Analytics: customizable KPI cards, period comparison, generated insights, channel/campaign drill-down.
- Modern financial dashboards: strong hierarchy, reconciliation status, explicit provisional vs final data.

Do not visually clone any brand. Use these interaction principles to create an original product UI.

## 41.2 Visual Language

Recommended style:

- clean, premium, minimal;
- neutral light background by default;
- optional dark mode;
- high information density without clutter;
- cards with subtle borders;
- large primary numbers;
- compact secondary comparison text;
- consistent 8px spacing system;
- clear typography hierarchy;
- minimal decorative elements.

Semantic status colors may be used:

- Green = healthy / profitable / improving
- Red = critical / losing / deteriorating
- Amber = warning / needs attention
- Blue = informational / opportunity / AI insight
- Gray = neutral / incomplete / insufficient data

Never use color as the only indicator. Pair color with icon/text/status.

## 41.3 Global Header

Persistent header:

```text
TikTok Shop Profit Control
[Shop ▼] [Today ▼] [Compare: Yesterday ▼]
[Product ▼] [Campaign ▼] [Source ▼] [Creator ▼]
Last sync: 14:02   Data Quality: 96%   [Refresh]
```

Required global filters:

- Shop
- Date range
- Comparison period
- Product
- SKU
- Campaign
- Ad Group
- Ad
- Video
- Creator/Affiliate
- Content source: Paid / Organic / Affiliate / Official / Marketing
- Classification: Winner / Promising / Warning / Loser / Fatiguing

Filters should persist in URL/query state so a filtered view can be shared.

## 41.4 Main Dashboard Information Architecture

The main page should be organized into seven vertical zones:

```text
1. BUSINESS HEALTH
2. AI DIAGNOSIS
3. SALES & PROFIT TREND
4. CAMPAIGN / PRODUCT / VIDEO PERFORMANCE
5. FUNNEL & ROOT CAUSE
6. TODAY'S PRIORITIES
7. TEAM ACTION BOARD
```

The page must read like a story:

```text
What happened?
↓
Where?
↓
Why?
↓
How much money is affected?
↓
What should we do?
↓
Who owns the action?
```

# 42. Zone 1 — Business Health

Top row contains the most important KPI cards.

Primary cards:

```text
Net Profit
GMV
Net Seller Revenue
Orders
Ad Spend
Net Margin
```

Secondary cards:

```text
Reported ROAS
Adjusted/Blended ROAS
AOV
CVR
Refund Rate
Settlement Coverage
```

Each card contains:

```text
Current value
% change vs comparison
absolute change
small sparkline
status
```

Example:

```text
NET PROFIT
Rp 1.84m
▲ 18.4% vs yesterday
+Rp 286k
[7-day sparkline]
HEALTHY
```

Clicking a KPI opens its diagnostic report.

## 42.1 Profit Health Score

Create a top-level score from 0–100.

It should NOT be an arbitrary AI score.

It must be deterministic and based on configurable components such as:

- net margin;
- profit trend;
- ad efficiency;
- conversion trend;
- refund rate;
- settlement/data quality.

Show the component breakdown on click.

Example:

```text
Profit Health: 78/100 — GOOD

Margin          88
Ad efficiency   74
Conversion      69
Refunds         92
Data quality    96
```

# 43. Zone 2 — AI Diagnosis

Immediately below KPIs place an **AI Business Diagnosis** panel.

It must be concise and prioritize no more than approximately 3–5 important findings.

Example:

```text
AI DIAGNOSIS — TODAY

🔴 Profit is down 14% vs yesterday.

Main causes:
1. Campaign "White Socks GMV Max" — spend +31%, orders +4%.
   Estimated impact: -Rp 218k.

2. Video #162 — CTR fell 2.4% → 1.1%.
   Likely creative fatigue.
   Estimated impact: -Rp 96k.

3. Product "Kids White 10" — CVR fell 5.2% → 3.4%.
   Traffic is stable; issue occurs after click.
   Check price/voucher/stock/product page.

🟢 Opportunity:
Video #184 generated Rp 615k estimated profit and is still improving.
Create 3–5 variants today.
```

Every diagnosis item must have:

- affected entity;
- metric change;
- baseline;
- estimated financial impact;
- confidence;
- CTA: `Investigate`, `Open video`, `Open campaign`, `Create task`.

# 44. Zone 3 — Sales & Profit Trend

Primary chart:

```text
GMV
Net Revenue
Net Profit
Ad Spend
```

Selectable granularity:

- Hour
- Day
- Week
- Month

Comparison overlay:

- previous period;
- previous week;
- custom period.

Important events should be shown as annotations when known:

- campaign budget changed;
- price changed;
- voucher started/ended;
- new creative launched;
- stockout;
- campaign paused;
- major refund;
- TikTok fee adjustment.

This allows the operator to visually connect business changes with performance changes.

## 44.1 Intraday Pace

For `Today`, include pace vs normal day:

```text
Today 14:00
Orders: 48

Expected by 14:00 based on last 4 comparable weekdays: 61

Pace: -21%
```

Do not compare partial current day against a complete previous day without normalization.

# 45. Zone 4 — Performance Explorer

Use tabs over the same analytical surface:

```text
Campaigns | Products | Videos | Creators
```

## 45.1 Campaign Table

Columns:

```text
Campaign
Status
Spend
Orders
GMV
Reported ROAS
Adjusted ROAS
Net Profit
Net Margin
CTR
CVR
Trend
AI Status
```

AI Status examples:

```text
SCALE
HEALTHY
WATCH
INVESTIGATE
REDUCE
```

Support sorting by:

- profit;
- spend;
- ROAS;
- margin;
- deterioration;
- opportunity score.

## 45.2 Product Table

Columns:

```text
Product / SKU
Units
Orders
GMV
Net Revenue
COGS
TikTok Fees
Affiliate Fees
Ads
Refunds
Net Profit
Margin
CVR
Trend
Status
```

## 45.3 Video Performance Gallery

This should be a visual gallery, not only a spreadsheet.

Each video card should show:

```text
[Video thumbnail]

Video #184
WINNER

Orders          37
GMV             Rp 2.7m
Ad Spend        Rp 410k
Net Profit      Rp 615k
CTR             3.8%
CVR             5.9%

▲ Profit +32%
```

Quick actions:

```text
View analysis
Compare
Open TikTok
Create variations
Assign to team
```

Filters:

```text
Winner
Promising
Traffic / No Sales
Low Attention
Fatiguing
Loser
```

## 45.4 Video Comparison

Allow selecting 2–5 videos.

Show side-by-side:

```text
Hook
Duration
Views
CTR
Clicks
CVR
Orders
GMV
Spend
CPA
Profit
Margin
Refund rate
Creator
Product
```

Phase 2 also includes creative-feature comparison:

```text
Product in first 2 sec?
Person visible?
Problem/solution?
Price shown?
Voucher shown?
CTA timing?
UGC/studio?
```

# 46. Zone 5 — Funnel & Root Cause

Display the selected business funnel:

```text
1,000,000 Views
     ↓ 3.2%
32,000 Product Clicks
     ↓ 7.1%
2,272 Orders
     ↓ 94%
2,136 Paid/Completed
     ↓
Settlement
```

For each step show:

- current conversion;
- baseline conversion;
- delta;
- estimated lost orders;
- estimated lost profit.

Example:

```text
PRODUCT CLICK → ORDER

Current: 3.4%
Baseline: 5.1%
Change: -33%

Estimated impact:
-21 orders
-Rp 387k potential profit

Primary affected product:
Kids White 10

Likely causes:
Voucher ended
Size 36–40 low stock
Product-page CVR deterioration
```

## 46.1 Root Cause Waterfall

Create a waterfall / contribution view for profit change.

Example:

```text
Yesterday Profit      Rp 2.10m
Campaign inefficiency -Rp 218k
CVR decline           -Rp 171k
Higher CPM            -Rp 64k
Refunds               -Rp 41k
Winner video growth   +Rp 232k
Other                 +Rp 2k
────────────────────────────
Today Profit          Rp 1.84m
```

The system must separate measured causes from estimated causes.

# 47. Zone 6 — Opportunity & Risk Queue

Two side-by-side panels.

## Opportunities

Rank by estimated profit upside:

```text
1. Scale/replicate Video #184
   Potential: +Rp 250–400k/day
   Confidence: HIGH

2. Increase exposure for Video #207
   Early winner; sample still small
   Potential: +Rp 120–220k/day
   Confidence: MEDIUM
```

## Risks / Leakage

Rank by money currently being lost:

```text
1. Campaign X inefficient spend
   Leakage: ~Rp 218k/day

2. Product Y conversion drop
   Estimated lost profit: ~Rp 171k/day

3. Video #162 fatigue
   Leakage: ~Rp 96k/day
```

This is important: prioritize by **money impact**, not by percentage change alone.

# 48. Zone 7 — Today's Team Action Board

This is a critical feature.

The dashboard must turn analytics into work for the team.

Board columns:

```text
TODAY
IN PROGRESS
REVIEW
DONE
```

Task types:

```text
DESIGN
VIDEO
PERFORMANCE MARKETING
PRODUCT
OPERATIONS
FINANCE
```

Each task card:

```text
Priority
Team
Task
Why
Source insight
Expected impact
Owner
Deadline
Status
```

Example:

```text
P1 — VIDEO TEAM

Create 3 variations of Video #184.

Why:
Current best profit-generating creative.
CTR +41% vs median.
CVR +28% vs product median.

Keep:
- first 2-second hook
- product demonstration
- pack quantity

Test:
- 3 different opening hooks

Expected impact:
+Rp 250–400k/day if performance holds.

Owner: Videographer
Deadline: Today 16:00
```

Design example:

```text
P1 — DESIGN TEAM

Create new cover/product visual for Kids White 10.

Why:
Traffic stable but product conversion down 33%.

Goal:
Improve click-to-order conversion.

Inputs:
Current winning visual references
Top converting SKU
Current price/voucher
```

Performance example:

```text
P1 — PERFORMANCE

Investigate Campaign "White Socks GMV Max".

Spend +31%
Orders +4%
Profit contribution -Rp 218k.

Do not automatically change campaign.
Review targeting/delivery/creative mix.
```

## 48.1 AI-Generated Daily Plan

Every morning or on demand, generate:

```text
TODAY'S SALES IMPROVEMENT PLAN

VIDEO TEAM
1. ...
2. ...

DESIGN TEAM
1. ...
2. ...

PERFORMANCE TEAM
1. ...
2. ...

PRODUCT/SHOP TEAM
1. ...

FINANCE
1. ...
```

Rules:

- maximum 3 high-priority tasks per team by default;
- every task must trace back to an observed metric/insight;
- no generic tasks like “improve creatives”;
- include expected impact where estimable;
- separate facts from hypotheses;
- user can accept/reject/edit/assign task;
- rejected recommendations should be logged for future evaluation.

# 49. Drill-Down Pages

Every major entity gets a dedicated page.

## Campaign Detail

Show:

- performance trend;
- ads/creatives;
- products sold;
- spend;
- GMV;
- reported and adjusted ROAS;
- net profit;
- anomalies;
- recommendation history;
- changes/events.

## Product Detail

Show:

- sales trend;
- price/voucher history where available;
- SKU performance;
- traffic funnel;
- videos selling this product;
- creators;
- refunds;
- fees;
- COGS;
- profit;
- conversion diagnostics.

## Video Detail

Show:

- video preview/thumbnail;
- creator/source;
- products;
- paid vs organic data where available;
- hourly/daily performance;
- CTR/CVR;
- orders;
- GMV;
- spend;
- profit;
- creative classification;
- fatigue chart;
- AI explanation;
- similar winning videos;
- tasks created from this video.

## Creator Detail

Show:

- videos;
- orders;
- GMV;
- affiliate commission;
- profit after commission;
- winning products;
- consistency;
- refund rate;
- recommended collaboration priority.

# 50. Management vs Team Views

Create saved dashboard presets.

## Executive View

Focus:

```text
Net Profit
GMV
Margin
Ad Spend
Adjusted ROAS
Top 3 problems
Top 3 opportunities
Today's plan
```

## Performance Marketing View

Focus:

```text
Campaigns
Ads
Spend
CPA
ROAS
Profit
Creative fatigue
Budget leakage
```

## Creative / Videography View

Focus:

```text
Winning videos
Losing videos
Hooks
Creative patterns
Products needing content
Today's briefs
Tasks
```

## Product / Commerce View

Focus:

```text
SKU sales
CVR
Price/voucher
Stock
Refunds
Profit
Product-page issues
```

## Finance View

Focus:

```text
Net seller revenue
Fees
Settlements
Payouts
Refunds
COGS
Profit
Reconciliation
```

All views use the same underlying source of truth.

# 51. Dashboard Interaction Requirements

Required:

- global date comparison;
- click-to-drill-down;
- hover tooltips explaining metrics;
- saved views;
- shareable filtered URLs;
- export CSV where useful;
- refresh status;
- data-quality badge;
- skeleton loading;
- empty states;
- error states;
- responsive layout;
- pagination/virtualization for large tables;
- server-side filtering for large datasets.

Do not render thousands of raw rows on initial load.

# 52. Insight-to-Task Workflow

Implement a first-class workflow:

```text
Metric Change
↓
Anomaly
↓
Root Cause Analysis
↓
AI Insight
↓
Recommendation
↓
Create Task
↓
Assign Team/Owner
↓
Execute
↓
Measure Result
```

A task created from an insight must preserve:

```text
source_insight_id
source_entity
baseline_metrics
created_metrics_snapshot
expected_impact
```

After completion, automatically evaluate the outcome after a configurable period.

Example:

```text
Task:
Create variants of Video #184

Completed:
Aug 30

Evaluation after 72h:
3 variants launched
2 received sufficient traffic
Variant B profitable
Incremental observed profit vs baseline: +Rp 310k

Result:
SUCCESS
```

This creates a learning loop between analytics and team execution.

# 53. Team Performance Learning Loop

The system should learn which recommendations actually work.

Store:

```text
recommendation
accepted/rejected
task
execution date
before metrics
after metrics
observed outcome
confidence
```

Over time calculate:

- recommendation acceptance rate;
- recommendation success rate;
- estimated vs observed impact;
- successful creative patterns;
- recurring causes of losses;
- average response time by team.

Do not use these metrics to punish individuals. The purpose is operational learning and better recommendations.

# 54. Dashboard Backend Endpoints

Suggested internal endpoints:

```text
GET /dashboard/overview
GET /dashboard/insights
GET /dashboard/trends
GET /dashboard/funnel
GET /dashboard/root-causes
GET /dashboard/opportunities
GET /dashboard/risks

GET /analytics/campaigns
GET /analytics/products
GET /analytics/videos
GET /analytics/creators

GET /campaigns/{id}
GET /products/{id}
GET /videos/{id}
GET /creators/{id}

GET /tasks
POST /tasks
PATCH /tasks/{id}

POST /recommendations/{id}/accept
POST /recommendations/{id}/reject
POST /recommendations/{id}/create-task
```

Use typed response schemas.

# 55. Dashboard Performance Requirements

Targets for normal filtered views:

```text
Overview initial API response: target < 1.5 sec
Filter interaction: target < 1 sec where cached
Drill-down: target < 2 sec
```

Use:

- pre-aggregated daily/hourly analytics tables;
- indexes;
- caching;
- background recalculation;
- materialized views where appropriate.

Do not calculate the entire historical business model synchronously on every dashboard request.

# 56. Dashboard Acceptance Criteria

The dashboard is accepted when a manager can open it in the morning and, without exporting data to Excel, identify:

1. Current sales.
2. Current real/estimated profit.
3. Comparison with yesterday/previous week.
4. Which campaign contributes most profit.
5. Which campaign is wasting money.
6. Which products are growing/falling.
7. Which videos are driving profitable sales.
8. Which videos are losing effectiveness.
9. Where the funnel is deteriorating.
10. The quantified likely causes.
11. The largest financial risks.
12. The largest opportunities.
13. Exactly what the design team should do today.
14. Exactly what the video team should do today.
15. Exactly what the performance team should investigate today.
16. Whether yesterday's recommended actions improved the result.

The dashboard is not considered complete if it only visualizes metrics.

It must convert:

> **DATA → DIAGNOSIS → PRIORITY → TEAM ACTION → MEASURED RESULT**

This workflow is a core product requirement.
