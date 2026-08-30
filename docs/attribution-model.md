# Advertising Attribution Model (Deliverable 4)

Source of truth: `src/analytics/attribution.py`. Every allocation result carries
`attribution_method` and `attribution_confidence`, and these are copied into `OrderProfit`
(SPEC §6.4). Order-level ad cost is always an **estimate** unless the method is
DIRECT_CREATIVE with an explicit link; it must never be displayed as exact.

## 1. The four numbers that must never be mixed (SPEC §7)

| Label            | Meaning                                                                     | Source                    |
|------------------|-----------------------------------------------------------------------------|---------------------------|
| Reported ROAS    | TikTok Ads / GMV Max reported attributed GMV ÷ spend, TikTok's own rules    | ad metrics API            |
| Attributed ROAS  | GMV of orders we can explicitly link to the creative/ad ÷ spend             | DIRECT_CREATIVE           |
| Adjusted ROAS    | Net seller revenue (after fees, refunds, discounts) of attributed orders ÷ spend | finance engine + attribution |
| Blended ROAS     | Total shop net revenue ÷ total ad spend, no attribution at all              | shop totals               |

GMV Max reports "supported" GMV that can include orders an ad merely touched; treat
`reported_gmv` as TikTok's claim, keep `direct_or_supported_attributed_gmv`, `organic_gmv`
and `blended_gmv` as separate columns, and never call anything "incremental" unless a
holdout/experiment supports causality (Phase 2, SPEC §30).

`roas(kind, revenue, spend)` returns a `LabeledRoas` whose `.label` is the display string;
spend of 0 yields `None`, never a division error or infinity.

## 2. Methods

| Method             | When                                                                 | Confidence            | Function            |
|--------------------|----------------------------------------------------------------------|-----------------------|---------------------|
| PLATFORM_REPORTED  | Use TikTok-reported spend/attribution per campaign/ad/creative as-is | HIGH (as *reported*)  | `platform_reported` |
| DIRECT_CREATIVE    | Ad ↔ video ↔ order link explicitly available; creative spend split across its linked orders by order value | HIGH; LOW if spend has no linked orders (all spend `unallocated`) | `direct_creative` |
| PROPORTIONAL       | No order-level link; spend split by attributed GMV (MEDIUM) or by order count (LOW) | MEDIUM / LOW; LOW if all weights are zero (equal split) | `proportional` |
| BLENDED            | Shop-level: `Blended Marketing Cost Ratio = Total Ad Spend / Net Revenue`, applied to each order's positive net revenue | LOW at order level (it is a ratio, not attribution) | `blended`, `blended_ratio` |

PLATFORM_REPORTED confidence is HIGH in the sense "the figure is exactly what TikTok reported";
it says nothing about causality — the result note always carries "reported, not incremental".

## 3. Reconciliation guarantee

All models use `allocate_proportionally`: shares are floored to the currency quantum
(IDR 1, USD 0.01), the remainder goes to the largest weight (ties → first input key), so
`Σ allocations == input spend` exactly. Spend that cannot be assigned (no linked orders,
undefined blended ratio, reported per-entity totals below campaign total) is returned in
`AttributionResult.unallocated`, never dropped. Orders with non-positive net revenue receive a
zero blended allocation.

## 4. Confidence levels

| Level  | Meaning                                                                                  |
|--------|------------------------------------------------------------------------------------------|
| HIGH   | Explicit link or exact reported figure; suitable for per-order profit with the method label |
| MEDIUM | Estimated split on a value basis (GMV); suitable for SKU/video/campaign aggregates       |
| LOW    | Estimated split on a weak basis (order count, zero weights, blended ratio) or unallocated spend; show only with an "estimate" caveat, never drive a stop/scale recommendation alone |

Recommendations inherit the lowest confidence of their inputs (SPEC §2.3, §13); incomplete
finance data (PROVISIONAL status) further downgrades.

## 5. Wording rules

* Always name the ROAS variant: "Reported ROAS 3.2", "Adjusted ROAS 1.9", "Blended ROAS 2.4".
* Never "ROAS" alone, never "incremental ROAS", never "this ad generated N profit" for
  PROPORTIONAL/BLENDED results — say "estimated allocated ad cost".
* Every report/dashboard cell showing ad cost or ROAS states `attribution_method` and
  `attribution_confidence`.

## 6. Example

Creative C1 spent 12,000 IDR and is explicitly linked to orders o1 (75,000) and o2 (25,000):
`direct_creative(12000, {o1: 75000, o2: 25000}, "IDR")` → `{o1: 9000, o2: 3000}`,
DIRECT_CREATIVE, HIGH. Feeding 9,000 into `order_profit` for o1 yields the §34 fixture profit
with 3,000 more headroom than the 12,000 flat example.

Shop day: ad spend 1,000, order net revenues {o1: 600, o2: 300, o3: −100} →
`blended_ratio = 1000/900 = 1.111111`, allocations `{o1: 667, o2: 333, o3: 0}`, BLENDED, LOW.
