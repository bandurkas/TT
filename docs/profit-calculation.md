# Profit Calculation (Deliverable 3)

Source of truth: `src/analytics/profitability.py`, `src/analytics/transaction_types.py`.
Deterministic, `Decimal` only, no ORM, no LLM. Amounts always carry a currency; mixing
currencies inside one order raises `CurrencyMismatchError` (no implicit FX, SPEC §21).

## 1. Formulas (SPEC §6.2)

```
Net Seller Revenue
  = sale_proceeds
  - seller_discounts
  - platform_fees            (platform commission + service fee + transaction fee)
  - affiliate_commission
  - shipping                 (seller-borne)
  - taxes                    (charged to seller)
  - refunds
  + platform_subsidies
  + adjustments              (signed: shipping / refund-fee / other adjustments)

Contribution Profit Before Ads
  = Net Seller Revenue - COGS - Packaging - Inbound Logistics - Other Variable Costs

Estimated Net Profit
  = Contribution Profit Before Ads - Allocated Advertising Cost
```

Internal per-unit costs come from the `CostVersion` effective on the order date
(`pick_cost_version`): `effective_from <= order_date < effective_to`, `effective_to = None`
is open-ended, overlapping versions resolve to the latest `effective_from`, no match raises
`CostVersionNotFoundError` (never silently zero COGS). Per-item cost = per-unit × quantity.

`UNKNOWN` transactions are **excluded** from every figure, but their count and summed raw amount
are reported (`RevenueBreakdown.unknown_amount/unknown_count`) and an `OrderProfit.warnings`
entry is added. They are never forced into another category (SPEC §5.7).

## 2. Transaction type mapping and sign table

Native names are canonicalized (lowercase, non-alphanumerics → `_`) and looked up in
`NATIVE_TO_NORMALIZED`; anything else → `UNKNOWN` with the native string preserved.
The native names listed are plausible, **UNVERIFIED** against live payloads.

| Normalized type          | Sign rule  | Effect on Net Seller Revenue     | Example native names (unverified)                 |
|--------------------------|------------|----------------------------------|---------------------------------------------------|
| SALE_PROCEEDS            | INCREASES  | `+abs(amount)`                   | sale, sales_revenue, order_revenue                |
| PLATFORM_SUBSIDY         | INCREASES  | `+abs(amount)`                   | platform_discount, platform_coupon, shipping_fee_subsidy |
| PLATFORM_COMMISSION      | REDUCES    | `-abs(amount)` (platform_fees)   | platform_commission, commission_fee, referral_fee |
| SERVICE_FEE              | REDUCES    | `-abs(amount)` (platform_fees)   | service_fee, platform_service_fee                 |
| TRANSACTION_FEE          | REDUCES    | `-abs(amount)` (platform_fees)   | transaction_fee, payment_fee                      |
| AFFILIATE_COMMISSION     | REDUCES    | `-abs(amount)`                   | affiliate_commission, creator_commission          |
| SHIPPING_FEE             | REDUCES    | `-abs(amount)`                   | shipping_fee, actual_shipping_fee                 |
| TAX                      | REDUCES    | `-abs(amount)`                   | tax, vat, sales_tax                               |
| REFUND                   | REDUCES    | `-abs(amount)`                   | refund, refund_amount, return_refund              |
| SELLER_DISCOUNT          | REDUCES    | `-abs(amount)`                   | seller_discount, seller_coupon                    |
| SHIPPING_ADJUSTMENT      | SIGNED     | `+amount` (as-is, may be < 0)    | shipping_adjustment, shipping_fee_adjustment      |
| REFUND_FEE_ADJUSTMENT    | SIGNED     | `+amount` (as-is)                | refund_fee_adjustment, refund_commission_reversal |
| OTHER_ADJUSTMENT         | SIGNED     | `+amount` (as-is)                | adjustment, settlement_adjustment, compensation   |
| UNKNOWN                  | EXCLUDED   | `0`, reported separately         | anything unmapped                                 |

Why `abs()` for directional types: TikTok may deliver a fee as `8000` or `-8000`; both mean
"seller pays 8,000". The direction is a property of the type, not of the payload sign.
Adjustments are the only sign-carrying category because their direction is unknowable from the
type alone. A `FinanceTxn` may also carry an explicit `normalized_type` (from ingestion config)
which overrides the native mapping.

## 3. Rounding rules

* No rounding is applied to sums: revenue, cost and profit totals are exact `Decimal` sums of
  the inputs (e.g. USD COGS `7.333 × 3 = 21.999` is kept, not rounded).
* Rounding happens **only** when a single amount must be split (order-level fees across items,
  ad cost across items/orders). `allocate_proportionally(total, weights, currency)`:
  1. share_i = floor(total × w_i / Σw) to the currency quantum (IDR → 1, USD → 0.01);
  2. remainder = total − Σ share_i is added to the largest weight (ties → first key in input
     order);
  3. therefore Σ allocations == total exactly, always.
  Negative totals are split by magnitude and re-signed. All-zero weights → equal split.
* Ratios (blended ratio, ROAS) are quantized to 6 decimal places.

## 4. Multi-SKU orders

* Transactions with `order_item_id` matching an item are applied to that item only.
* Order-level transactions (no/unknown `order_item_id`) are summed into one net figure and split
  across items proportionally by `gross_item_value = unit_sale_price × quantity` using the
  rule above. Allocated ads are split the same way.
* Guarantee: `Σ item.net_seller_revenue == order.net_seller_revenue`,
  `Σ item.allocated_ad_cost == order.allocated_ad_cost`,
  `Σ item.estimated_net_profit == order.estimated_net_profit`.

## 5. Profit status (SPEC §6.3)

Derived by `derive_profit_status`, precedence top to bottom:

| Status      | Rule                                                                                  |
|-------------|---------------------------------------------------------------------------------------|
| REFUNDED    | `sale_proceeds > 0` and `refunds >= sale_proceeds`                                    |
| PROVISIONAL | no SALE_PROCEEDS transaction, or any SALE_PROCEEDS transaction lacks `settlement_id`  |
| ADJUSTED    | settled, and an adjustment-type transaction exists whose `settlement_id` is not one of the sale's settlements (i.e. arrived after/outside settlement) |
| PAID        | settled and every SALE_PROCEEDS transaction has a `payout_id`                        |
| SETTLED     | otherwise                                                                             |

A partial refund does not change status by itself. Historical profit is mutable (SPEC §20):
recompute whenever new transactions arrive; the caller is responsible for versioning results.

## 6. Guards

* Duplicate `external_transaction_id` inside one order → `DuplicateTransactionError`
  (use `duplicate_transaction_ids` / `dedupe_transactions` at ingestion; the engine never
  silently double-counts).
* Any currency mismatch between items, transactions, cost versions or ads →
  `CurrencyMismatchError`.
* Empty item list → `ValueError`.

## 7. Worked example (SPEC §34 fixture, IDR)

Inputs: 1 × LOMIRA-WHITE-5 at 75,000; transactions `sale 75,000`, `platform_commission 8,000`,
`affiliate_commission 5,000` (all with settlement s1); cost version from 2026-08-01:
COGS 25,000, packaging 1,500; allocated ads 12,000 (DIRECT_CREATIVE, HIGH).

```
Net Seller Revenue            = 75,000 - 8,000 - 5,000            = 62,000
Contribution Profit Before Ads= 62,000 - 25,000 - 1,500           = 35,500
Estimated Net Profit          = 35,500 - 12,000                   = 23,500
profit_status = SETTLED   attribution_method = DIRECT_CREATIVE   attribution_confidence = HIGH
```

Variants (tested): partial refund 20,000 → 3,500 (SETTLED); full refund → −51,500 (REFUNDED);
adjustment +1,000 in settlement s2 → 24,500 (ADJUSTED); adjustment −2,000 → 21,500 (ADJUSTED);
no settlement ids → 23,500 but PROVISIONAL; order dated 2026-07-15 with older COGS 20,000 →
28,500.
