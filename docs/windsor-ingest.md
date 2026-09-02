# Windsor.ai → GMV Max daily Cost ingest

Automates what an operator has been typing by hand. Replaces neither the Ads app (§3.2) nor the
manual form: it closes *past* days automatically; the day in progress stays manual.

## 1. What the source actually gives (measured 2026-09-02, not read off a datasheet)

`GET https://connectors.windsor.ai/tiktok?api_key=…&date_from=…&date_to=…&fields=…` → `{"data":[…]}`.

Populated for this advertiser: `date`, `account_name`, `account_id` / `advertiser_id`
(`7658353454934671368`), `campaign`, `campaign_id`, `gmv_max_ads_spend`, `gmv_max_ads_billed_cost`.

Everything else we need is **null**: `creative_id`, `video_id`, `material_id`, `ad_id`,
`adgroup_name`, `product_id`, `product_name`, `gmv_max_ads_orders`, `_gross_revenue`, `_roi`,
`_budget`, and — importantly — `currency` and `timezone`. `impressions` / `clicks` / `conversions`
come back `0`, which is not the same as measured zero and is therefore **not stored**.

Three behaviours the design has to survive:

1. **GMV Max is a separate report type.** Asking for plain `spend` returns `{"data":[]}` for this
   account, because every campaign is GMV Max. The query must always carry a GMV Max field.
2. **An unknown field name returns `{"data":[]}` with HTTP 200 and no error.** A typo is therefore
   indistinguishable from "no spend" — the exact failure mode that already cost this shop 885,857 of
   unrecorded Cost. See §3.
3. **Their "today" trails the shop's.** At 02:18 WIB on 2026-09-02 the API's today was 2026-09-01, and
   a `date_from` past it is a hard error. The window must be clamped, not assumed.

## 2. Flow

```
WindsorClient.fetch_gmv_max(from,to)
   └─ raw_api_responses   (integration "windsor", resource "gmv_max_daily")   § SPEC 2.2
        └─ normalize: rows -> per-day totals + per-campaign rows
             ├─ ad_accounts / campaigns        (external IDs preserved)       § SPEC 5.13
             ├─ ad_metrics entity_type=campaign, spend, metric_date           § SPEC 5.14
             └─ shop_ad_days via SourceReport scope "windsor_gmv_max"
                  └─ profit recompute + daily aggregates
```

No migration: `ad_accounts`, `campaigns` and `ad_metrics` already exist with the needed shape.

## 3. The rules that keep it honest

- **An absent date is never written as zero.** Only dates the response actually contains are touched.
  A day Windsor does not mention keeps whatever it had — including "no data at all", which the
  dashboard already renders as `—` rather than as profit.
- **A null is not a zero.** The connector answers `null` for any field it cannot fill. A null
  `gmv_max_ads_spend` costs **its own day and nothing else**: that day is dropped whole — writing the
  sum of the campaigns that *did* report would understate it — and listed in `skipped_null_days`. It becomes an
  `errors` entry — the thing `/health` reads — **only when no settled Cost is on file for that day**
  (a day still `partial` is not a fallback): with
  nothing to fall back on the day is genuinely missing, whereas a day that already has a Cost simply
  gained no new information, and holding the job red across the whole backfill window for that would
  mask the next real failure. `/health` renders only the first line, so errors are ordered by blast radius: an
  unusable `account_id` (the whole window loses its campaign detail), then per-day rejections, then
  null days. All of them are assembled before the day loop, so a crash inside it cannot lose them. Only
  `date` and `campaign_id` are fatal to the request, because a row cannot be grouped without them.
  Blankness is emptiness, not just `None`: an empty-string `account_id` would pass an `is None` test
  and then silently skip the whole campaign branch.
- **An empty or malformed response writes nothing** and fails the job loudly into
  `integration_sync_state` (`job:ads_windsor`), so `/health` shows it. Every row must carry every
  requested key; a response whose rows lack `gmv_max_ads_spend` is treated as a contract change, not
  as zero spend.
- **Only a newer observation replaces a day** — the same rule the XLSX and manual paths use. A Windsor
  row supersedes an earlier manual entry for a closed day; it can never overwrite something observed
  later.
- **One bad day never truncates the window.** A day whose write is rejected is collected into
  `errors` (which `/health` reads through `_collect_errors`) and the remaining days are still
  ingested; only "a newer observation already exists" is swallowed, since that is the normal result
  of a re-run.
- **The operator guard does not run on this path.** `_check_manual_day` exists to catch a human typing
  a period's totals into one day; Windsor is the platform's own figure and must be allowed to correct
  a bad manual entry *downward*. Instead, a material disagreement with the stored value is logged and
  returned in the job result, so it is visible rather than silent.
- **Currency and timezone are assumed, and said so.** Windsor returns null for both, so the shop's own
  `IDR` / `Asia/Jakarta` are asserted and the SourceReport records `timezone_basis:
  "operator_confirmed"`, exactly as the XLSX import does. Empirical support: 25 consecutive days
  matched our independently sourced figures to the rupiah.
- **The open day stays partial.** `final` is set only for days that have ended in the shop timezone.

## 4. Scheduling and configuration

`ads_windsor` runs hourly at :25 (shop tz), refetching a rolling window that **ends on the last day
that has ended in the shop's timezone** and starts `WINDSOR_BACKFILL_DAYS` earlier (default 7) so late
restatements are picked up. Yesterday, not `min(shop_today, windsor_today)`: the connector's clock
trails ours and rejects a later date outright, and the open day belongs to the manual form anyway.
A day whose stored Cost and finality already match is not rewritten — `observed_at` is inside the
content hash, so writing an unchanged day would insert a report and force a full profit recompute
every tick. Its **per-campaign split is still refreshed**, because a campaign-mix restatement keeps
the same total while moving the split, and a day first entered by hand has no campaigns at all until
this runs. Conversely, when a day's Cost is *rejected*, its campaign rows are not written either:
`ad_metrics` must never outlive the Cost it splits. Recorded in `integration_sync_state` as `job:ads_windsor`, stale after 3h.

`WINDSOR_API_KEY` lives only in `/root/TT/.env`. **With no key the job is skipped, not failed** — dev
and CI never reach the network.

## 5. What this deliberately does not do

- No creative-, video-, product- or ad-level cost: Windsor returns null for all of them, so SPEC §5.15
  `creative_mappings` still waits on our own Ads app and its `gmv-max-ads-reports` endpoint.
- No orders / revenue / ROAS from the ad side: null as well. Attribution stays BLENDED (§6.4 D).
- No writes to TikTok. Read-only, per §2.4.
