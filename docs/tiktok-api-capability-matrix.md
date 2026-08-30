# TikTok API Capability Matrix (Deliverable 1) — DRAFT v0.2 (2026-08-30, offline)

Status values: AVAILABLE / NOT AVAILABLE / REQUIRES APPROVAL / REGION LIMITED / UNKNOWN /
**documented, unverified** (= path found in official doc index or official SDK, never called live).

Partner Center docv2 pages are JS-rendered and could not be read offline; paths below come from
the official page slugs (which embed path + version), the Finance/Products API overview snippets,
and the open-source SDK EcomPHP/tiktokshop-php (mirrors docv2). Ads paths come from the official
`tiktok/tiktok-business-api-sdk`. Scope names for TikTok Shop are the Partner Center "Manage API"
category labels, not verified API scope identifiers. Everything is re-verified in Deliverable 5.

Shop base URL: `https://open-api.tiktokglobalshop.com`; version is embedded in the path
(`/{category}/{version}/{resource}`); auth header `x-tts-access-token`; signed with `sign` query
param (see `src/integrations/tiktok_shop/signing.py`). Ads base URL:
`https://business-api.tiktok.com/open_api/v1.3`, header `Access-Token`.

| Data Point | API | Endpoint | Scope | Granularity | Freshness | Available? | Notes |
|---|---|---|---|---|---|---|---|
| Shop info (shop_cipher, region) | Shop / Authorization | `GET /authorization/202309/shops` | Shop Authorized Info | per authorized shop | on demand | documented, unverified | Needed first: provides `cipher` for all other calls |
| Products / SKUs | Shop / Product | `POST /product/202309/products/search` (query page_size/page_token); `GET /product/202309/products/{id}` | Product | product, SKU nested | on demand | documented, unverified | SKU seller_sku expected inside product detail; field names UNKNOWN |
| Orders | Shop / Order | `POST /order/202309/orders/search`; `GET /order/202309/orders?ids=` | Order | order + line items | near-real-time (webhooks exist) | documented, unverified | Filter names create_time_ge/lt, update_time_ge/lt, order_status UNVERIFIED; sort_field/sort_order in query |
| Video performance | Shop / Data Insights (Analytics) | `GET /analytics/{202405\|202409\|202509}/shop_videos/performance` (list); `/shop_videos/overview_performance`; `/shop_videos/{id}/performance` | Data Insights / Analytics (name UNKNOWN) | per video, daily window (`start_date_ge`/`end_date_lt`) | UNKNOWN (docs mention T+1 style lag; unverified) | documented, unverified | Docv2 lists revisions 202409 and 202509; SDK uses 202405. Which one ID region supports — UNKNOWN |
| Video-product performance | Shop / Data Insights | `GET /analytics/202405/shop_videos/{video_id}/products/performance` | Data Insights | per video × product | UNKNOWN | documented, unverified | version UNVERIFIED |
| Product performance | Shop / Data Insights | `GET /analytics/202405/shop_products/performance`; `/shop_products/{id}/performance`; `/shop_skus/performance` | Data Insights | product / SKU, daily window | UNKNOWN | documented, unverified | Docv2 "Shop Product Performance Detail" page exists |
| Shop performance | Shop / Data Insights | `GET /analytics/202405/shop/performance` | Data Insights | shop, daily window | UNKNOWN | documented, unverified | docv2/page/get-shop-performance-202405 |
| LIVE performance | Shop / Data Insights | `GET /analytics/202508/shop_lives/overview_performance` | Data Insights | shop-level LIVE overview | UNKNOWN | documented, unverified | Page get-shop-live-performance-overview-202508; per-LIVE list endpoint UNKNOWN |
| Affiliate / creator | Shop / Affiliate Seller | `POST /affiliate_seller/{ver}/orders/search` (+ open/target collaborations, marketplace_creators/search 202406) | Affiliate Seller | per affiliate order / creator | UNKNOWN | UNKNOWN | Category slug and body UNVERIFIED; client raises NotImplementedError. May REQUIRE APPROVAL for ID |
| Finance transactions / statements | Shop / Finance | `GET /finance/202309/statements`; `GET /finance/202309/statements/{id}/statement_transactions` (v202501 revision exists); `GET /finance/202309/orders/{order_id}/statement_transactions` | Finance | statement (settlement batch) → order-level transactions | settlement lag: statement created after order completes (days); provisional until paid | documented, unverified | ONBOARDING open question: Finance scope for ID without extra approval — UNKNOWN |
| Settlements | Shop / Finance | same as statements (`payment_status` filter) | Finance | statement | as above | documented, unverified | `get_settlements` = alias of statements |
| Payouts | Shop / Finance | `GET /finance/202309/payments`; `GET /finance/202309/withdrawals?types=WITHDRAW,SETTLE,TRANSFER,REVERSE` | Finance | payment / withdrawal record | after bank payout | documented, unverified | Finance overview: "payment details for a date range" |
| Refunds / returns | Shop / Return & Refund | `POST /return_refund/202309/returns/search`; `POST /return_refund/202309/cancellations/search` | Return & Refund | per return/cancellation | near-real-time | documented, unverified | Category slug `return_refund` UNVERIFIED |
| Campaign / ad group / ad | Ads (Marketing API v1.3) | `GET /campaign/get/`, `GET /adgroup/get/`, `GET /ad/get/` (advertiser_id, filtering, page, page_size, fields) | Ads Management (read) | object-level; status, budget, optimization fields | real-time config | documented, unverified | Official SDK `tiktok-business-api-sdk`; page_info.total_page pagination |
| Advertiser account | Ads | `GET /advertiser/info/` (advertiser_ids[], fields) | Ad Account Management (read) | account | on demand | documented, unverified | currency/timezone come from here |
| Ad report (spend, impressions, clicks, CTR, CPC, CPM, conv, GMV, ROAS) | Ads / Reporting | `GET /report/integrated/get/` (service_type=AUCTION, report_type=BASIC, data_level=AUCTION_CAMPAIGN\|AUCTION_ADGROUP\|AUCTION_AD, dimensions, metrics, start_date, end_date, page) | Reporting | campaign/adgroup/ad × day (or hour) | intraday; TikTok reattribution can restate recent days — treat last 7d as provisional | documented, unverified | Metric names (spend, impressions, clicks, ctr, cpc, cpm, conversion, onsite_shopping…) UNVERIFIED; async `/report/task/*` exists for large ranges |
| GMV Max report | Ads / Reporting | `GET /gmv_max/report/get/` (advertiser_id, store_ids[], dimensions, metrics, start_date, end_date); alt: `/report/integrated/get/` with report_type=TT_SHOP | Reporting (+ GMV Max enabled on account) | campaign/product × day | UNKNOWN | documented, unverified | Portal page gmv-max-ads-reports/v1.3 exists but JS-rendered; ONBOARDING open question whether the account has GMV Max. Attribution ≠ Shop attribution (SPEC §7) |
| Creative ↔ video ID mapping | Ads / Creative | `GET /ad/get/` (video_id field on ad, UNVERIFIED); `GET /file/video/ad/info/` (video_ids ≤60); `GET /file/video/ad/search/` | Creative Management (read) | per ad / per video asset | on demand | documented, unverified | Mapping Ads `video_id` → TikTok Shop `shop_videos` id (Data Insights) is UNKNOWN; Spark Ads use organic post id — verify live |

## UNVERIFIED items (must be confirmed in Deliverable 5)
- Signature algorithm details (hex case, body inclusion for GET) — from third-party SDK, not read from official page.
- `access_token_expire_in` unit (unix seconds assumed) in token responses.
- All Shop body/query filter field names and response `items` keys (`orders`, `products`, `videos`, `statements`, `transactions`, `payments`, `withdrawals`, `return_orders`, `next_page_token`).
- Analytics version (202405 vs 202409 vs 202509) and Data Insights scope name for region ID.
- Affiliate Seller and Return & Refund category slugs.
- Ads: data_level values, metric/dimension names, GMV Max metrics, `video_id` field on `/ad/get/`.
- Ads: whether `Access-Token` header vs `access_token` query is required (SDK lists query; portal docs use header) — client sends header.

## Sources consulted (2026-08-30)
- https://partner.tiktokshop.com/docv2/page/get-order-list-202309 (slug only, JS-rendered)
- https://partner.tiktokshop.com/docv2/page/search-products-202309
- https://partner.tiktokshop.com/docv2/page/authorization-guide-202309
- https://partner.tiktokshop.com/docv2/page/finance-api-overview
- https://partner.tiktokshop.com/docv2/page/get-statements-202309
- https://partner.tiktokshop.com/docv2/page/get-transactions-by-order-202309
- https://partner.tiktokshop.com/docv2/page/new-version-v202501-for-statement-transactions-and-order-statement-transactions
- https://partner.tiktokshop.com/docv2/page/get-withdrawals-202309
- https://partner.tiktokshop.com/docv2/page/get-shop-video-performance-list-202509
- https://partner.tiktokshop.com/docv2/page/get-shop-video-performance-details-202409
- https://partner.tiktokshop.com/docv2/page/get-shop-video-performance-overview-202509
- https://partner.tiktokshop.com/docv2/page/get-shop-performance-202405
- https://partner.tiktokshop.com/docv2/page/get-shop-live-performance-overview-202508
- https://partner.tiktokshop.com/docv2/page/create-hash-to-sign-your-test-api-call (JS-rendered)
- https://github.com/EcomPHP/tiktokshop-php (src/Client.php signing; Resources/{Finance,Analytics,Order,Product,Authorization,ReturnRefund,AffiliateSeller}.php)
- https://github.com/hookdeck/webhook-skills/blob/main/skills/tiktok-shop-webhooks/references/verification.md (confirms API signing ≠ webhook signing)
- https://github.com/tiktok/tiktok-business-api-sdk (python_sdk/docs/{ReportingApi,CampaignCreationApi,AdgroupApi,AdApi,AccountManagementApi,FileApi}.md, README)
- https://business-api.tiktok.com/portal/docs/gmv-max-ads-reports/v1.3 (JS-rendered; search snippet: report_type=TT_SHOP, service_type=AUCTION)
- https://business-api.tiktok.com/portal/docs/get-gmv-max-campaigns/v1.3
- https://core.telegram.org/bots/api#sendmessage

## Prerequisites (Phase 0 checklist)
- [ ] TikTok Shop Partner Center developer account, app created, region ID
- [ ] Shop authorized to the app; scopes list recorded
- [ ] TikTok for Business developer app; advertiser authorized
- [ ] Finance scope availability for this seller account confirmed
- [ ] Response samples saved to `tests/fixtures/` (PII stripped)
