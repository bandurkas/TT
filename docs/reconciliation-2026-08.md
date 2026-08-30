# Deliverable 6 — Reconciliation vs Seller Center (August 2026)

Source: Seller Center → Finance → Income export `income_20260830221550(UTC+7).xlsx` (period 2026/08/01–08/30, UTC+7)
vs API `GET /finance/202309/orders/{id}/statement_transactions` (live, 2026-08-30).

## Result: 12/12 orders match exactly (settlement, revenue, total fees)

| Order | Source | Revenue | Fees | Settlement (XLSX) | Settlement (API) |
|---|---|---|---|---|---|
| 585649789132637561 | Tokopedia | 91,000 | −9,520 | 81,480 | 81,480 |
| 585617420006360209 | TikTok Shop | 91,000 | −16,072 | 74,928 | 74,928 |
| 585615568104490414 | TikTok Shop | 100,000 | −11,170 | 88,830 | 88,830 |
| 585588423474579252 | TikTok Shop | 0 (full refund) | 0 | 0 | 0 |
| 585625312034653821 | TikTok Shop | 91,000 | −9,520 | 81,480 | 81,480 |
| 585615511133325145 | TikTok Shop | 100,000 | −9,940 | 90,060 | 90,060 |
| 585598525834495045 | TikTok Shop | 100,000 | −10,240 | 89,760 | 89,760 |
| 585583340052055265 | TikTok Shop | 100,000 | −11,170 | 88,830 | 88,830 |
| 585579844588504809 | TikTok Shop | 100,000 | −16,840 | 83,160 | 83,160 |
| 585641188963484967 | Tokopedia | 0 (refund, fees kept) | −10,250 | −10,250 | −10,250 |
| 585583943233078299 | TikTok Shop | 100,000 | −10,240 | 89,760 | 89,760 |
| 585656874805134466 | Tokopedia | 91,000 | −16,345 | 74,655 | 74,655 |
| **Total** | | | | **832,693** | **832,693** |

Identity confirmed on every row: `settlement_amount = revenue_amount + fee_amount + adjustment_amount`.

## Field mapping XLSX ↔ API (confirmed)
| Seller Center column | API field |
|---|---|
| Total settlement amount | `settlement_amount` |
| Total Revenue | `revenue_amount` |
| Subtotal before discounts | `gross_sales_amount` |
| Seller discounts | `seller_discount_amount` |
| Total Fees | `fee_amount` (aggregate) |
| Dynamic commission | (inside fee_amount; API exposes `platform_commission_amount`=0 here → dynamic commission is NOT broken out separately in API — derive as fee_amount − other components) |
| Order processing fee | not a separate API field observed → part of residual |
| Logistics service fee / Shipping cost | `shipping_cost_amount` |
| Shipping costs passed on to logistics provider | `actual_shipping_fee_amount` |
| Shipping cost borne by the platform | `platform_shipping_fee_discount_amount` |
| Shipping cost paid by the customer | `customer_shipping_fee_amount` − `shipping_fee_amount` |
| Affiliate Commission | `affiliate_commission_amount` |
| Platform discount | `platform_discount_amount` |
| Customer payment | `customer_payment_amount` |
| Refund subtotal | `gross_sales_refund_amount` / `customer_refund_amount` |
| Article 22 Income Tax withheld | `pit_amount` / `isr_income_tax_amount` (monthly −2,500, not seen on these orders) |

## Advertising is charged from the payout
6 rows `Transaction type = "GMV payment for TikTok Ads"` (adjustment IDs, e.g. 3690566883990537287, −421,800 on 2026-08-29). Monthly Reports sheet: Revenue 2,755,000 · Fees −353,515 · **Adjustments −2,495,139** · **Total settlement −93,654** → in August the shop paid out negative: GMV Max ad spend deducted from settlements exceeded net sales. These deductions are the primary ad-cost source of truth for profit (SPEC §6.2) and must be ingested (withdrawals API `type=…` / statements adjustments — see capability matrix).

## Consequences for the finance engine
- Use the per-order statement record (field-based) as the settled truth; `fee_amount` is aggregate — components: affiliate, shipping cost, dynamic commission (residual), order processing fee (residual).
- Ad cost = GMV Max payout deductions (shop-level, daily) → allocate PROPORTIONAL/BLENDED to orders; plus Ads API report for per-campaign breakdown once available.
- Marketplace `Order source` (TikTok Shop / Tokopedia) is in the export; API equivalent `commerce_platform` on order.
