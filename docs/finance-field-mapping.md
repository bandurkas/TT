# Finance API field mapping — statement record → profit engine

Source: `GET /finance/202309/orders/{id}/statement_transactions` (live 2026-08-30, ID shop, IDR).
The API returns **one flat record per order** with ~60 named amount fields plus
`sku_statement_transactions[]` (same fields per SKU), not a list of typed transactions.
Adapter: `src/analytics/finance_fields.py` → `list[FinanceTxn]` for `src/analytics/profitability.py`.
Verification: `tests/unit/test_finance_fields.py` on `tests/fixtures/tiktok_shop/august_statements.json`
(12 August orders) — engine `net_seller_revenue == settlement_amount == Seller Center
"Total settlement amount"` 12/12, total 832,693.

## Identities verified on real data (12/12)

```
settlement_amount = revenue_amount + fee_amount + adjustment_amount
revenue_amount    = gross_sales_amount + seller_discount_amount
                  + gross_sales_refund_amount + seller_discount_refund_amount      (net_sales_amount == revenue_amount)
fee_amount        = affiliate_commission_amount + shipping_cost_amount + RESIDUAL
RESIDUAL          = Seller Center "Dynamic commission" + "Order processing fee"     (matches 12/12)
0                 = actual_shipping_fee_amount + platform_shipping_fee_discount_amount
                  + customer_shipping_fee_amount + customer_paid_shipping_fee_refund_amount
shipping_fee_amount = −(customer_shipping_fee_amount + customer_paid_shipping_fee_refund_amount)
platform_discount_amount does NOT change revenue_amount (91,000 = 100,000 − 9,000 while platform discount −3,640)
```

Sign convention in the API: seller-receives positive, seller-pays negative. The engine applies its own
sign rules by type (`abs()` for directional types, signed for adjustments), so the payload sign is
never load-bearing except for `adjustment_amount` and `seller_discount_refund_amount`.

## Roles

| Role | Emitted as FinanceTxn? | Meaning |
|---|---|---|
| revenue / refund / fee / adjustment | yes | components that add up to `settlement_amount` |
| aggregate | no | sums of other fields (`revenue_amount`, `fee_amount`, `settlement_amount`, `net_sales_amount`) — emitting would double count |
| passthrough | no | customer/platform/logistics shipping money that nets to zero for the seller |
| info | no | buyer-side or derived figures (customer payment, platform discount, …) — kept in raw payload |
| linkage | no | ids/status/time/currency → `settlement_id`, txn id prefix |
| sku | no | per-SKU split and metadata |

Unknown field → logged warning; if it is a non-zero amount it is emitted as `UNKNOWN` (excluded from
every figure, counted in `RevenueBreakdown.unknown_count`). Never raises.

## Field table

Seller Center column = Finance → Income export (`income_20260830…xlsx`), see `reconciliation-2026-08.md`.
"Sign" = sign observed in the API payload. "UNVERIFIED" = only `0` observed in August; classification is
by name and by the identity (anything that reduces settlement must live inside `fee_amount` or
`adjustment_amount`), not by data.

| API field | Meaning | Sign | Normalized type | Role in formula | Seller Center column |
|---|---|---|---|---|---|
| `gross_sales_amount` | listed value of items sold | + | SALE_PROCEEDS | + sale_proceeds | Subtotal before discounts |
| `seller_discount_amount` | seller-funded discount | − | SELLER_DISCOUNT | − seller_discounts | Seller discounts |
| `gross_sales_refund_amount` | refunded item value (before seller discount) | − | REFUND | − refunds | Refund subtotal before seller discounts |
| `seller_discount_refund_amount` | seller discount returned on refund | + | REFUND_FEE_ADJUSTMENT | + adjustments (signed) | Refund of seller discounts |
| `revenue_amount` | Total Revenue (= gross + sdisc + refunds) | ± | — | aggregate, not emitted | Total Revenue |
| `net_sales_amount` | == revenue_amount in all samples | ± | — | aggregate, not emitted | (Subtotal after seller discounts − refunds) |
| `after_seller_discounts_subtotal_amount` | buyer-view subtotal incl. customer shipping | + | — | info | Subtotal after seller discounts (+shipping) |
| `platform_discount_amount` | platform-funded discount (platform tops up seller) | − | PLATFORM_SUBSIDY | info — **not emitted**, already inside gross | Platform discount |
| `platform_discount_refund_amount` | platform discount reversed on refund | − | PLATFORM_SUBSIDY | info | Platform discount refund |
| `platform_refund_subsidy_amount` | UNVERIFIED | 0 | PLATFORM_SUBSIDY | info | — |
| `fee_amount` | Total Fees (aggregate) | − | — | aggregate; drives residual | Total Fees |
| `platform_commission_amount` | platform commission (0 in ID; commission lives in residual) | 0 | PLATFORM_COMMISSION | − platform_fees (fee component) | Dynamic commission (not broken out) |
| `referral_fee_amount` | UNVERIFIED | 0 | PLATFORM_COMMISSION | fee component | — |
| `transaction_fee_amount` | UNVERIFIED | 0 | TRANSACTION_FEE | fee component | Order processing fee? (in residual) |
| `affiliate_commission_amount` | affiliate/creator commission | − | AFFILIATE_COMMISSION | − affiliate_commission (fee component) | Affiliate Commission |
| `affiliate_commission_before_pit` | affiliate commission before PIT withholding | − | AFFILIATE_COMMISSION | info (== amount when pit=0) | — |
| `affiliate_ads_commission_amount` | UNVERIFIED | 0 | AFFILIATE_COMMISSION | fee component | — |
| `affiliate_partner_commission_amount` | UNVERIFIED | 0 | AFFILIATE_COMMISSION | fee component | — |
| `shipping_cost_amount` | seller-borne logistics service fee | − | SHIPPING_FEE | − shipping (fee component) | Shipping cost / Logistics service fee |
| `shipping_insurance_fee_amount` | UNVERIFIED | 0 | SHIPPING_FEE | fee component | — |
| `signature_confirmation_fee_amount` | UNVERIFIED | 0 | SHIPPING_FEE | fee component | — |
| `return_shipping_fee_amount` | UNVERIFIED | 0 | SHIPPING_FEE | fee component | — |
| `fbm_shipping_cost_amount` | UNVERIFIED | 0 | SHIPPING_FEE | fee component | — |
| `fbt_shipping_cost_amount` | UNVERIFIED | 0 | SHIPPING_FEE | fee component | — |
| `fbt_fulfillment_fee_amount` | UNVERIFIED | 0 | SERVICE_FEE | fee component | — |
| `fbt_fulfillment_fee_reimbursement_amount` | UNVERIFIED | 0 | SERVICE_FEE | fee component | — |
| `refund_administration_fee_amount` | UNVERIFIED | 0 | SERVICE_FEE | fee component | — |
| `retail_delivery_fee_amount` | US-only; UNVERIFIED | 0 | SERVICE_FEE | fee component | — |
| `sales_tax_amount` | UNVERIFIED | 0 | TAX | − taxes (fee component) | — |
| `isr_income_tax_amount` | Article 22 income tax withheld; UNVERIFIED per order | 0 | TAX | fee component | Article 22 Income Tax withheld |
| `iva_vat_amount` | UNVERIFIED | 0 | TAX | fee component | — |
| `pit_amount` | PIT withheld; UNVERIFIED | 0 | TAX | fee component | Article 22 Income Tax withheld |
| `fee_residual` (synthetic) | `fee_amount − Σ fee components` | − | PLATFORM_COMMISSION | − platform_fees | Dynamic commission + Order processing fee |
| `adjustment_amount` | order-level adjustment | ± | OTHER_ADJUSTMENT | ± adjustments (signed) | Adjustment amount |
| `settlement_amount` | Total settlement amount | ± | — | aggregate; test target | Total settlement amount |
| `actual_shipping_fee_amount` | shipping passed on to logistics provider | − | — | passthrough | Shipping costs passed on to the logistics provider |
| `platform_shipping_fee_discount_amount` | shipping borne by platform | + | — | passthrough | Shipping cost borne by the platform |
| `customer_shipping_fee_amount` | shipping paid by customer | + | — | passthrough | Shipping cost paid by the customer |
| `customer_paid_shipping_fee_amount` | == customer_shipping_fee_amount | + | — | passthrough | Customer shipping cost before discounts (net) |
| `customer_paid_shipping_fee_refund_amount` | customer shipping refunded | − | — | passthrough | Refunded shipping cost paid by the customer |
| `shipping_fee_amount` | −(customer shipping + its refund) | − | — | passthrough | — |
| `customer_shipping_fee_offset_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `shipping_fee_subsidy_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `shipping_cost_discount_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `refund_shipping_cost_discount_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `promo_shipping_incentive_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `actual_return_shipping_fee_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `retail_delivery_fee_payment_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `retail_delivery_fee_refund_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `sales_tax_payment_amount` | customer-paid tax; UNVERIFIED | 0 | — | passthrough | — |
| `sales_tax_refund_amount` | UNVERIFIED | 0 | — | passthrough | — |
| `customer_payment_amount` | buyer paid value (SPEC §6.1 level 2) | + | — | info | Customer payment |
| `customer_refund_amount` | buyer refunded | − | — | info | Customer refund |
| `customer_order_refund_amount` | == customer_refund_amount | − | — | info | — |
| `id` | statement transaction id | | — | txn id prefix `{id}[:{sku_id}]:{field}` | — |
| `statement_id` | statement (settlement) id | | — | `FinanceTxn.settlement_id` when status SETTLED/PAID | Order settled time (statement) |
| `statement_time` | unix seconds | | — | linkage | Order settled time |
| `status` | `SETTLED` observed | | — | not settled → `settlement_id=None` → PROVISIONAL | — |
| `currency` | IDR | | — | linkage | Currency |
| `sku_statement_transactions[]` | per-SKU copy of the fields + `sku_id`, `sku_name`, `product_name`, `quantity` | | — | exact per-SKU split | Details of items sold |

## Residual rule

`fee_amount` is an aggregate; Indonesia's *dynamic commission* and *order processing fee* have no
dedicated API field (`platform_commission_amount = 0`). The adapter emits every FEE-role field it can
see and then

```
fee_residual = fee_amount − Σ(all FEE-role fields, including zero ones)
```

as one `PLATFORM_COMMISSION` txn (`native_type="fee_residual"`, note
"dynamic commission + order processing fee (residual)"). Consequences:

* Σ(fee txns) always equals `fee_amount` by construction — no double count, and a fee field that
  is later mis-classified only moves money between fee buckets, never out of the total.
* Residual matched the export's `Dynamic commission + Order processing fee` on 12/12 orders
  (−8,530 with seller discount, −9,250 without; −1,250 processing fee is inside).
* If TAX fields ever appear **outside** `fee_amount` the identity breaks; the adapter logs
  `identity broken` and the reconciliation test fails — re-derive from data before changing roles.

## Per-SKU split

When `sku_statement_transactions[]` is present and its `settlement/revenue/fee/adjustment` sums
equal the order record, txns are emitted per SKU with `order_item_id = sku_to_item[sku_id]`
(default: the `sku_id`), each SKU carrying its own residual. Otherwise order-level txns are emitted
and the engine's proportional split (`allocate_proportionally`) applies.

## Profit status linkage

`statement_id` → `settlement_id` on every txn when `status ∈ {SETTLED, PAID}`; the engine derives
SETTLED (or PAID when a `payout_id` from the payments endpoint is passed), REFUNDED when
`gross_sales_refund_amount` covers the sale (both August refunds: 0 and −10,250 with fees kept).
A non-settled status leaves `settlement_id=None` → PROVISIONAL.

## Statements list (`GET /finance/202309/statements`)

`classify_statement(row)`: `revenue_amount == 0 and fee_amount == 0 and adjustment_amount < 0` →
`AD_DEDUCTION` (GMV Max ad spend charged from payout; export type "GMV payment for TikTok Ads",
August: −421,800, −444,000, −98,235, −98,152, −58,846, −1,110,000; API samples −64,972, −29,353);
`revenue != 0 or fee != 0` → `ORDER_SETTLEMENT`; else `OTHER` (e.g. positive adjustment, monthly
Article 22 −2,500 would be OTHER until matched). Accepts either API keys or export columns. Keep
AD_DEDUCTION rows labelled UNVERIFIED until amount+date match the export.
