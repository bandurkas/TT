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

## Follow-up: the operator's actual goal is 100 orders/day, profitable

What the data says about that target (measured unless marked):

- **Demand is almost entirely paid.** GMV Max share of GMV averages 75.6 % by day; affiliate is
  77k of 6.2M in August. Of GMV, 86 % arrives through the product card and 14 % through video; video
  funnel in August: 59,826 views → 3,847 clicks (6.4 %) → 8 orders (**0.21 %** click→order).
- **Paid demand has strongly diminishing returns.** Between the two measured regimes, orders scale
  with budget at elasticity **0.44** (1.0 would be linear). Extrapolating that curve to 100 orders/day
  gives an absurd budget — the point is not the number but the shape: buying 100/day from the same
  single campaign on the same product card is not a budget question, it is a different machine.
- **Best measured CPO is 33.9k** (130k/day). Break-even CPO: 50.5k at today's COGS, 62k at 15k COGS,
  65k at 12k COGS. So at any COGS in the grid, 100 profitable orders/day needs the *marginal* order
  to cost ≤ ~62–65k — while the marginal order already costs ~105k at 6/day.
- At 100 orders/day the permitted ad budget is **5.1–6.9M/day** depending on COGS, and the daily
  profit ranges from +1.7M (today's COGS, CPO 34k) to −0.8M (today's COGS, CPO 59k).

Conclusion: 100/day profitably is reachable only by changing where demand comes from and what each
order carries — not by turning the GMV Max budget up. In order of leverage:

1. **Contribution per order up**: ≤ 3,000/pair purchasing (keeps the 5-pair winner), and a bigger
   basket — 89 of 99 orders are a single set; a 2-set bundle at a small discount raises revenue per
   order without raising CPO. Both measurable within a week.
2. **Cheaper demand**: organic/affiliate video, creator seeding, live — the only sources whose CPO is
   not on the 0.44 curve. Today they are ~24 % of GMV. Requires content volume; the Ads app's
   creative-level data is what will tell which videos to feed.
3. **Scale paid in steps with a hard guard**: +50k/day at a time, hold ≥ 3 days, continue only while
   trailing-3-day CPO ≤ break-even for the COGS in force. The dashboard already shows daily CPO.
4. **More products / campaigns**: one campaign, one product card carries ~90 % of everything; a second
   winner doubles reachable demand at the *low* end of the CPO curve instead of climbing the high end.

None of this is a forecast of 100/day. It is what must be true for it to be profitable when it comes.

## Follow-up 2 (2026-09-02 afternoon): purchase price ≈ 4,000/pair; what ad budget; did the 80k price help?

**Price cut to 80,000 — not visible in the data yet.** Net revenue per unit (after platform
deductions, before fees): 27–31 Aug 72.9–78.3k; 1–2 Sep 73.7–78.3k; price points unchanged (75k/80k).
1 Sep's 8 orders came on the highest budget ever (450k); 28 Aug also had 8 on 323k with no price
change; 2 Sep had 3 by 14:00. Two factors moved at once and n = 8 — no conclusion either way.
The settled `revenue_base` will show the cut once orders placed at the new price flow through.

**COGS with 4,000/pair:** the selling unit is the 5-pair set → **20,000** (not 12,000; that is a
3-pair set, a different product). Contribution at August revenue: 52,476/unit → break-even CPO
57,193; at the late-August revenue actually being realised (~76k/unit): 46,804 → break-even CPO 51,011.

**Budget under the measured curve** (orders/day = 0.0226 · budget^0.44, two points, one week each —
a guardrail, not a forecast):

```
кривая по двум точкам: заказов/день = 0.02259 · бюджет^0.44   (130,771→3.86; 344,919→5.89)

выручка/ед: 82,453 = средняя августа; 76,000 = фактическая 27.08–02.09 (медианы 72.9–78.3k)

=== выручка/ед 82,453 | 5×4000 = 20,000 → вклад/ед 52,476, безубыточный CPO 57,193
  оптимум прибыли: бюджет ≈    75,919/день → 3.0 зак/день, CPO 24,953, прибыль ≈   +98,091/день
  потолок (прибыль=0): бюджет ≈   330,654/день → 5.8 зак/день, CPO 57,193
  бюджет/день:   100,000   130,000   150,000   200,000   250,000   300,000   345,000   450,000
  заказов/день:      3.4       3.8       4.1       4.6       5.1       5.5       5.9       6.6
  прибыль/день:  +96,235   +90,034   +84,209   +65,530   +42,680   +16,913    -8,162   -71,761

=== выручка/ед 82,453 | 3×4000 = 12,000 → вклад/ед 60,476, безубыточный CPO 65,912
  оптимум прибыли: бюджет ≈    97,648/день → 3.4 зак/день, CPO 28,757, прибыль ≈  +126,167/день
  потолок (прибыль=0): бюджет ≈   425,294/день → 6.5 зак/день, CPO 65,912
  бюджет/день:   100,000   130,000   150,000   200,000   250,000   300,000   345,000   450,000
  заказов/день:      3.4       3.8       4.1       4.6       5.1       5.5       5.9       6.6
  прибыль/день: +126,151  +123,578  +119,914  +106,010   +87,300   +65,226   +43,189   -14,098

=== выручка/ед 76,000 | 5×4000 = 20,000 → вклад/ед 46,804, безубыточный CPO 51,011
  оптимум прибыли: бюджет ≈    61,976/день → 2.8 зак/день, CPO 22,256, прибыль ≈   +80,076/день
  потолок (прибыль=0): бюджет ≈   269,926/день → 5.3 зак/день, CPO 51,011
  бюджет/день:   100,000   130,000   150,000   200,000   250,000   300,000   345,000   450,000
  заказов/день:      3.4       3.8       4.1       4.6       5.1       5.5       5.9       6.6
  прибыль/день:  +75,024   +66,250   +58,893   +36,828   +11,044   -17,343   -44,571  -112,645

=== выручка/ед 76,000 | 3×4000 = 12,000 → вклад/ед 54,804, безубыточный CPO 59,730
  оптимум прибыли: бюджет ≈    81,995/день → 3.1 зак/день, CPO 26,060, прибыль ≈  +105,942/день
  потолок (прибыль=0): бюджет ≈   357,119/день → 6.0 зак/день, CPO 59,730
  бюджет/день:   100,000   130,000   150,000   200,000   250,000   300,000   345,000   450,000
  заказов/день:      3.4       3.8       4.1       4.6       5.1       5.5       5.9       6.6
  прибыль/день: +104,940   +99,794   +94,598   +77,308   +55,664   +30,971    +6,780   -54,982
```

Reading it: profit per day peaks at a small budget (60–100k/day, ~3 orders) and reaches zero at
270–330k/day for the 5-pair set at 20,000 COGS. Between 130k and 200k/day the curve is nearly flat
(+66k…+37k/day at 76k revenue) — that band buys ~0.8 extra orders/day for ~70k, roughly at cost.
Above ~250k/day every order is bought at a loss on this curve.

**Recommendation for the coming week (5-pair set, 20,000 COGS):**
- Hold **150–200k/day**: near the profit plateau, still growing volume, and enough spend to read a
  CPO signal daily. Do not run 300k+ until the curve is shown to have moved.
- **Guard:** trailing-3-day CPO must stay ≤ 51k (76k revenue) / ≤ 57k (82k revenue). Above it, step
  the budget down 50k; below 35k for three days, step up 50k.
- The curve moves only if conversion moves: the price test and a 2-set bundle are what to measure
  this week, budget held constant so the effect is attributable. If the 80k price lifts orders per
  budget, the whole table shifts right and the plateau widens — that is the lever toward 100/day.

## Follow-up 3: the budget is two campaigns, not one

Per-campaign daily spend (Windsor, `ad_metrics`) next to total orders. Orders per campaign are
**not available** — Windsor returns null for GMV Max orders, so CPO is only measurable on the total.

| date | majority black | moms & girls | total | orders | CPO |
|---|---|---|---|---|---|
| 17–23 Aug | 130,000/day | — | 130,000 | 27 in 7 days | 33.9k |
| 24 Aug | **303,833** | — | 303,833 | 3 | 101k |
| 25–27 Aug | 342–350k | — | ~345k | 6/6/5 | 57–70k |
| 28 Aug | 300,000 | 22,802 | 322,802 | 11 | 29k |
| 29–31 Aug | 232–300k | 39–77k | 310–344k | 5/3/6 | 57–103k |
| 1 Sep | 387,504 | 62,496 | 450,000 | 8 | 56k |

- The break in CPO is **24 Aug, when "majority black" alone went 130k → 300k**. "moms & girls" did
  not exist yet; it started 28 Aug at 23–77k/day and has spent 245,590 in total against 3.77M for
  "majority black". The whole high-regime finding is about the main campaign's budget.
- With blended orders, the second campaign cannot be judged on its own. Its one useful signal is
  28 Aug: the day it started was the best day of the high regime (11 orders, CPO 29k) — but one day,
  and the main campaign's spend was unchanged, so it may be coincidence.

**Recommendation restated per campaign:**
- **majority black: back to 130–150k/day** — the regime in which it was measured profitable at the
  current COGS, and the level from which the 24 Aug step broke CPO. This is the whole adjustment.
- **moms & girls: hold at its ~100k cap**, do not raise; it is the experiment. Combined total lands at
  230–250k/day — above the 150–200k band from follow-up 2, which is acceptable only because the
  second campaign is the test being run; if trailing-3-day total CPO exceeds 51k, it is the one to
  cut first, since the main campaign's 130k level has a measured record and it does not.
- To judge "moms & girls" properly, either the Ads app (attributed orders per campaign) or an A/B
  by days: run it on alternate days for two weeks with the main campaign fixed, and compare orders
  on its on-days vs off-days. Blended attribution cannot do better than that.

## Follow-up 4 (2026-09-03): campaign analysis, last 3 days — and a correction

**Correction.** Windsor *does* report GMV Max orders, gross revenue, ROI, cost per order, the
configured budget, and a per-product breakdown inside each campaign. The 2026-09-02 probe used the
wrong field names (`gmv_max_ads_orders`…), and the connector answers an unknown field with nothing,
not an error. The real fields, from `get_fields`: `gmv_max_cost`, `gmv_max_net_cost`,
`gmv_max_orders`, `gmv_max_gross_revenue`, `gmv_max_roi`, `gmv_max_cost_per_order`,
`gmv_max_target_roi_budget`, `gmv_max_max_delivery_budget`, `gmv_max_product_id`,
`gmv_max_live_room_id`. `video_id` is still null for GMV Max. Raw tables:
`docs/campaign-analysis-2026-09-03.txt`.

Note on attribution: orders/revenue here are TikTok's, "paid and organic attributed to the
campaign"; they track the shop's own order count closely (28 Aug: 10 vs 11; 1 Sep: 10 vs 8;
2 Sep: 6 vs 6). ROI is gross revenue ÷ cost, before fees and COGS. **Break-even ROI for the shop**
at ~78k revenue/unit: 1.81 at today's COGS, 1.61 at 4,000/pair, 1.38 at 12,000.

| 31 Aug – 2 Sep | budget | spend | orders | revenue | ROI | CPO |
|---|---|---|---|---|---|---|
| majority black | 300k | 918,687 | 17 | 1,342,143 | **1.46** | 54,040 |
| moms and girls | 100k | 144,524 | 4 | 308,568 | **2.14** | 36,131 |
| LIVE GMV Max (started 2 Sep) | 200k | 38,261 | 1 | 34,022 | 0.89 | 38,261 |
| total | | 1,101,472 | 22 | 1,684,733 | 1.53 | 50,067 |

Previous 3 days (28–30 Aug): majority black ROI 1.71 / CPO 52k; moms and girls ROI 1.09 / CPO 72k.

- **majority black is under break-even five days out of six** (ROI 2.59 → 1.42 → 0.97 → 1.55 →
  1.70 → 0.95). Only 28 Aug cleared 1.81. The campaign is capped at 300k and spends it whether or
  not the day converts — 30 Aug and 2 Sep bought 2–3 orders for 230k.
- **Inside majority black, 90 % of spend goes to the black 5-pair hit (ROI 1.71, 32 orders); the
  other seven products took 149,761 over six days for one order.** Five of them have zero orders:
  ~25k/day, 9 % of the campaign, buying nothing.
- **moms and girls is above break-even over the last 3 days (2.14)** but on a 3-day sample with
  4 orders; over 6 days it is 1.62 — right at the 4,000/pair break-even. Inside it, grey 5-pair
  carries it (ROI 2.02, 4 orders), the kids' 10-pair had one order at ROI 2.99, and **the
  black/white mix took 30 % of the campaign (87,546) for zero orders**.
- **LIVE**: one room on 2 Sep, 38k spent, one order, ROI 0.89. First day; nothing to conclude. The
  product breakdown only sees 6.9k of the 38k — the rest is attributed to the live room, not to a
  product — so judge LIVE by `gmv_max_live_room_id`, not by product.

**Actions this suggests (operator's call):** exclude the five zero-order products from majority
black and the black/white mix from moms and girls (≈ 40k/day currently buying nothing, ~12 % of
spend); keep moms and girls at 100k as the one campaign clearing break-even; bring majority black's
cap down toward the 130–150k regime from follow-up 3 — its ROI has been below 1.81 on every day it
spent 300k except one. Give LIVE three more days before reading it.

**Next engineering step:** extend `ads_windsor` to ingest these fields → `ad_metrics.attributed_orders`,
`attributed_gmv`, `reported_roas` per campaign and per product (SPEC §5.14), which makes §6.4 A
"platform reported" attribution available instead of BLENDED, and puts campaign ROI vs break-even
on the dashboard daily.

## Follow-up 5 (2026-09-03): "will a higher ROI get us to 100/day?", shop traffic, price 65,000

**Traffic.** Not measurable for GMV Max through Windsor: `impressions`, `clicks`, and every
`onsite_*` field (product page views, add-to-cart, checkout) come back 0 for GMV Max campaigns on
every day 17 Aug – 2 Sep. Shop-level visitors are not in the Shop API either (product-card
impressions/clicks NOT AVAILABLE). The only traffic we hold is **video** (14 % of GMV):

| regime | video views/day | product clicks/day | CTR | video-attributed orders/day |
|---|---|---|---|---|
| 130k (17–23 Aug) | 619 | 12 | 1.96 % | 0.4 |
| 300k+ (24 Aug – 1 Sep) | 5,840 | 565 | 9.68 % | 0.5 |

Video traffic rose ~9× with the budget; video orders did not move. 30 Aug alone: **48,126 views,
5,226 product clicks, 0 video orders, 3 shop orders in total** — a click-to-order rate under 0.06 %.
Traffic is not what is missing; conversion after the click is. For shop visitors, read Seller
Center → Analytics and the GMV Max dashboard in Ads Manager directly; we cannot pull them.

**Does raising ROI get to 100/day?** No — ROI is a ratio, 100/day is volume. ROI above break-even is
the *condition* under which budget can be scaled without losing money; it does not create demand by
itself. The measured curve says scaling the main campaign 130k → 300k dropped ROI below break-even.
So the order is: (1) raise ROI at the current scale — product exclusions (≈ 40k/day on zero-order
products), offer/price, creatives; (2) then step the budget up while ROI holds ≥ threshold; (3) add
demand sources that are not on the same curve (second/third campaign, LIVE, organic/affiliate). At
CPO 50–65k, 100 orders/day is 5–6.5M/day of spend; nothing measured yet shows ROI holding there.

**Price 65,000** (lowest allowed). Net revenue/unit ≈ price × 0.96 (80k lists as 76–78k in the
order base). Contribution and thresholds:

| list price | net/unit | contribution @25,515 | @20,000 | break-even CPO @20,000 | break-even ROI @20,000 |
|---|---|---|---|---|---|
| 80,000 | 76,800 | 41,992 | 47,507 | 51,783 | 1.62 |
| 72,000 | 69,120 | 35,241 | 40,756 | 44,425 | 1.70 |
| **65,000** | 62,400 | 29,335 | 34,850 | **37,986** | **1.79** |

The cut costs **12,658 per unit** at either COGS. At today's CPO (~50k) it makes every order less
profitable unless conversion rises **≥ 34 %** on the same budget (CPO ≤ 37.4k). Note the direction:
a lower price *raises* the ROI threshold (1.62 → 1.79), because each order carries less margin.
Nothing in the data yet shows the 80k cut lifting orders per budget (n = 8, confounded with the 450k
day). 65k is therefore a bet on elasticity ≥ 34 % with no measurement behind it — run it as a
bounded test (one campaign or one listing, budget fixed, 5–7 days, judge by orders-per-budget), not
as the shop's new price.
