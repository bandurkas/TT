# Profit job — real profit from ingested data

Code: `src/domain/profit/jobs.py`, `src/domain/profit/aggregates.py`, `src/db/models_profit.py`,
CLI `apps/worker/profit_cli.py`, migration `c7f3a9d2e514_profit_daily` (revises `c7d2a9f14e58`); `e2a5c8d1b7f3` adds `shop_config.default_cogs_per_unit` and the partial unique index `uq_order_profit_one_current` (one current row per order).
Engine and formulas: `docs/profit-calculation.md`; field adapter: `docs/finance-field-mapping.md`;
attribution: `docs/attribution-model.md`. Decimal only, no LLM.

## Pipeline (`compute_order_profits(session, shop_id, since=None)`)

1. **Load** (`load_inputs`): orders (+items) of the shop — with `--since`, from `since − 7 days`
   so the ad window sees full trailing revenue; `order_statement_records` with status
   `SETTLED|PAID` — **all** records per order (restatements/refunds land as extra statements;
   warning `N settled statements for order`) + their SKU records; the unsettled placeholder record
   (`statement_id ""`) when no settled one exists; `sku_cost_versions` keyed by external sku id;
   all `settlements`; `shop_config.default_cogs_per_unit`.
   **Incremental (`--since`)**: only deductions with local day ≥ since are allocated and only orders
   with local date ≥ since are persisted; look-back orders serve as allocation weights only, so
   the result equals the full run for those orders.
2. **Settled orders** → `record_to_dict` (ORM row → API-shaped dict incl.
   `sku_statement_transactions`) → `finance_fields.statement_record_to_txns` → `FinanceTxn`s
   (`sku_id → order_items.id` mapping). Engine `net_seller_revenue == settlement_amount`; if the
   emitted txns do not reproduce it, warning `MISMATCH statement …` + `inputs_snapshot.mismatch`.
   Txns of all settled statements are concatenated → later adjustments give status `ADJUSTED`.
3. **Provisional orders** (no settled record, status not `CANCELLED/UNPAID` — names UNVERIFIED):
   if an unsettled statement record with non-zero `revenue_amount` exists it is mapped like a
   settled one but without `settlement_id` (`inputs_snapshot.source = unsettled_record`); else
   → `estimate_provisional` (`source = ratio_estimate`): sale = `gross_merchandise_value` (or Σ items) − `seller_discount`,
   fees = sale × **trailing 30-day fee ratio** (`Σ|fee_amount| / Σ revenue_amount` of settled
   records with `revenue_amount > 0` and a `statement_time`, as of the latest statement date). No `settlement_id` → engine status `PROVISIONAL`;
   first warning is always `PROVISIONAL ESTIMATE: …`, `inputs_snapshot.estimate = true`.
   No fee history → fees 0 + warning. This is an estimate, never a settlement figure.
4. **COGS**: `pick_cost_version(effective_from ≤ order local date)`; quantity from `order_items`
   (fallback: statement SKU records). Missing version → warning `COGS missing for sku …`;
   cogs = `shop_config.default_cogs_per_unit` if set (`inputs_snapshot.cogs_default_used = true`,
   set via `profit_cli config --default-cogs 25000`) else 0; `cogs_missing = true` either way
   (never silently hidden, never raises). Engine errors (currency mismatch, duplicate txn) skip that
   order only (`skipped`/`errors` in the CLI result).
5. **Ad cost** (see below) → `AllocatedAds(BLENDED, LOW)`; `order_profit(...)` per order.
6. **Persist** (`persist_order_profits`): `analytics_order_profit` is versioned. The
   `inputs_snapshot` carries a sha256 `hash` of material inputs only (txns, items, cost versions,
   ad cost, status, local date, source, mismatch, fee ratio at 4 dp; Decimal strings are
   exponent-normalised; warning wording is excluded). If the
   current row has the same hash → no-op; otherwise previous row `is_current=False`, insert
   `version = prev + 1`. `attribution_method='BLENDED'`, `attribution_confidence='LOW'` always
   (no per-campaign data yet). Per-item split (product_id, qty, net revenue, cogs, ads, profit)
   is stored in `inputs_snapshot.items` for product aggregates.
7. **Aggregates** (`aggregates.recompute_daily`): affected local dates are recomputed into
   `analytics_shop_daily` (unique shop_id+metric_date) and `analytics_product_daily`
   (unique product_id+metric_date) via upsert. `gmv` on the shop level = `shop_metrics.gmv_total`
   when present, else Σ sale_proceeds. `fees` = platform fees + seller shipping + taxes;
   `affiliate` separate; `cogs` includes packaging/inbound/other; `net_margin` =
   net_profit / net_seller_revenue (None when revenue ≤ 0). Product level: order-level
   fees/affiliate/refunds are spread by gross_item_value share (deterministic, IDR-rounded).

Business day = order `order_created_at` in shop timezone (`shops.timezone`, default Asia/Jakarta).

## Ad cost: BLENDED over a trailing 7-day window

Source: `settlements` rows that are GMV Max payout deductions — `extra.classification ==
'AD_DEDUCTION'` if the ingest set it, else `gross_amount == 0 and net_amount < 0`
(`finance_fields.classify_statement` on `extra` when available). Summed per **shop-local
settlement day** (`ad_deductions_by_day`).

Why a window and not per-day: deductions are lumpy — August 2026 export shows −1,110,000 on
08/23, −444,000/−98,235/−98,152/−58,846 on 08/27, −421,800 on 08/29 (total −2,231,033) while the
underlying spend accrued over the preceding days. Charging a single day's orders with 1.11M would
produce absurd per-order losses and zero ad cost on neighbouring days. So each deduction day's
spend is spread with `attribution.blended` over orders whose local date lies in
`[day − 6, day]`, weighted by positive net seller revenue (negative/refunded orders get 0).
Guarantee: `Σ allocated + unallocated == Σ deductions`; unallocated (no revenue in window) is
logged, never dropped silently. Confidence is **LOW** and every row/report says so.

This is a placeholder for attribution: once the Ads API report is ingested (per campaign / creative
spend + reported GMV), per-order allocation moves to `PLATFORM_REPORTED` / `DIRECT_CREATIVE` /
`PROPORTIONAL` and the payout deductions become the reconciliation target for total spend.

## CLI

```
python -m apps.worker.profit_cli compute                     # all orders of the first shop
python -m apps.worker.profit_cli compute --since 2026-08-01  # orders from 2026-07-25 (window)
python -m apps.worker.profit_cli report --month 2026-08      # table: date, orders, net revenue, fees, cogs, ads, net profit, margin + totals
python -m apps.worker.profit_cli --json report --month 2026-08
python -m apps.worker.profit_cli --shop-id 1 compute
```

On VPS3: `cd /root/TT && docker compose run --rm worker alembic upgrade head` then the commands above
inside the worker container (`docker compose run --rm worker python -m apps.worker.profit_cli …`).

## Assumptions (UNVERIFIED)

* Order statuses to skip for provisional estimates: `CANCELLED`, `CANCEL`, `UNPAID`.
* `order_statement_records.status` values `SETTLED|PAID` are the only settled states.
* Ad-deduction detection by `gross_amount == 0 and net_amount < 0` may catch other negative
  adjustment-only statements (e.g. monthly Article 22 −2,500) until ingest sets
  `extra.classification`. Match amounts/dates against the Seller Center export before trusting totals.
* `gross_merchandise_value` on orders is the pre-discount sale value used for provisional revenue.
* 7-day window and 30-day fee-ratio window are chosen, not measured.
