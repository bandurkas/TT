# Pricing / COGS / ad-budget study — 2026-09-02

Question from the operator: after playing with the What-if panel, "3 pieces per set at 4,000 IDR a
pair looks profitable" — is that the optimum, and what is the best strategy overall?

## Data used (production, all measured)

- 99 orders 2026-07-22 … 2026-09-01 (97 calculated; 2 cancelled). **89 of 99 orders are one unit**,
  10 are two. **97 of 109 line items are the black 5-pair set** ("Socks Kaos Kaki Pria Hitam 5
  Pasang"). The selling unit is, in practice, one 5-pair set.
- Revenue per unit after refunds, before fees: median 91,000; points cluster at 75k / 80k / 90k / 100k.
- Fees 12.1 % of revenue (median 12.4 %). Refunds: 5 orders (5 %), 490,000 total.
- August unit economics (97 units): revenue 82,453 · fees 10,584 · COGS
  25,515 (seed default 25,000 ≈ 5 × 5,104 — no real purchase lots yet) · **ad cost
  50,328** → net **−3,974 per unit**. Ad cost is 61 % of revenue.
- Ad cost per day now comes from Windsor (GMV Max, per campaign), so the daily series is real.

## The finding that matters: it is the ad budget, not the socks

Two clearly different regimes in the daily series:

| regime | budget/day | orders/day | cost per order | ad cost per unit |
|---|---|---|---|---|
| 17–23 Aug (~130k/day) | 130,771 | 3.86 | **33,904** | 31,107 |
| 24 Aug – 1 Sep (300–450k/day) | 344,919 | 5.89 | **58,571** | 53,741 |

Raising the budget 2.6× bought 2.03 extra orders/day for 214,148 extra IDR/day — **105,401 IDR
per marginal order**, against a contribution of 46,354 per unit at today's COGS. Every extra
order in the high regime loses about 59,047. 21–23 Aug (130k/day, CPO 22–27k) were
profitable days at the *current* COGS; 24, 27, 29, 30, 31 Aug were the loss days, all at 300k+.

Break-even, current COGS 25,515: ad cost ≤ **46,354 per unit ≈ CPO ≤ 50,500 per order**.
The low regime is under it; the high regime is 16 % over it.

## Break-even COGS per unit, by ad regime

| regime | ad/unit | COGS must be ≤ |
|---|---|---|
| low (130k/day) | 31,107 | **40,762** — current 25,515 is already fine |
| August average | 50,328 | 21,541 |
| high (345k/day) | 53,741 | **18,128** — this is the regime in which "3 × 4,000 = 12,000" looks necessary |

The operator's intuition is right *given the high-budget regime*: at 12,000 COGS the unit clears
+6,128 (7.4 %) even at 345k/day. But the same 12,000 at 130k/day clears +28,762 (34.9 %), and the
current 25,515 at 130k/day already clears +15,762 (19.1 %).

## Grid (net per unit; full table in the session log)

- COGS 12,000 (3×4,000 / 4×3,000 / 2×6,000): +28,762 low · +6,128 high · +9,541 August-avg
- COGS 15,000 (5×3,000 / 3×5,000): +25,762 · +3,128 · +6,541
- COGS 9,000 (3×3,000): +31,762 · +9,128 · +12,541
- COGS 25,515 (today): +15,762 · **−6,872** · −3,974

Monthly at August-like volume, net profit:

| | low regime (~130 units) | high regime (~199 units) | August as it was (97) |
|---|---|---|---|
| COGS today 25,515 | **+1,987k** | −1,470k | −385k |
| 3 × 4,000 = 12,000 | +3,748k | +1,219k | +926k |
| 5 × 3,000 = 15,000 | +3,357k | +622k | +635k |
| 3 × 3,000 = 9,000 | +4,139k | +1,816k | +1,217k |

## What is NOT measured (do not read the grid as if it were)

- **Demand response.** Every cell holds revenue, fees and ad cost at their actual values and moves
  only COGS. "3 pairs instead of 5" is a different product at (presumably) a different price; how
  many people buy it, and at what CPO, is unknown. The panel and this grid cannot answer that.
- **Quality vs. cost.** 4,000 → 3,000 per pair is a purchasing decision; refunds are 5 % today.
  A cheaper sock that lifts refunds to 10 % eats most of the gain (refunds are ~5,000/unit now).
- **Sample size.** The low regime is one week, 27 orders. Its CPO is real but not a guarantee.
- COGS itself is still the seed 25,000: no purchase lots exist. Real invoice prices may already be
  lower — enter them in "Per-SKU cost" before deciding anything on the cost side.

## Recommendation, in order

1. **Ad budget back toward the 130k/day regime, and scale only while CPO stays ≤ 46k** (break-even
   at today's COGS) — this alone turns August-shaped months from −385k into ≈ +2M. It is the only
   lever with measured evidence behind it, and it is reversible day by day.
2. **Cost side: keep the 5-pair set, negotiate per-pair down.** 5 × 3,000 = 15,000 keeps the product
   that actually sells (97 of 109 items) and its price points untouched, while clearing +3k/unit even
   in the high regime and +25.8k in the low one. Prefer this over shrinking to 3 pairs, which changes
   the offer and its demand — unmeasured.
3. **3 × 4,000 is not wrong**, it is a smaller product at the same 12,000 COGS as 4 × 3,000. If the
   5-pair set can be bought at ≤ 3,000/pair, the 3-pair variant buys nothing extra on cost and risks
   the demand you have. Consider it only if a 3-pair set can hold the same ~80k price — test it as a
   separate listing, not by replacing the winner.
4. Enter real purchase lots. Every number above moves with the first invoice.

Ad regime × 5×3,000 is the combination with measured support: ≈ +3.4M/month at low-regime volume.
