# Dashboard API (SPEC §54) — implemented in `apps/api/dashboard.py`

All routes under `/api`. Query params (all optional): `shop_id`, `from`, `to` (ISO dates, shop-local; default = current month to today), `cmp_from`, `cmp_to` (default = previous period of equal length). Money and ratios are **Decimal serialised as strings** (never float); ratios are fractions (0.1156 = 11.56%). Every response carries `shop`, `period`, `compare`, `generated_at`.

| Route | Zone | Payload |
|---|---|---|
| `GET /api/dashboard/overview` | 1 | `cards[]` (key, kind money/count/pct/ratio, value, prev, change_abs, change_pct, sparkline[7], status good/warn/bad/neutral, note, provisional), `health` {score, grade, components{margin, ad_efficiency, conversion, refunds, data_quality}}, `unit_economics`, `data_quality` {score, state, reasons, last_sync, freshness_minutes}, `totals`, `notes[]` |
| `GET /api/dashboard/trends` | 3 | `series[]` per day {date, gmv, net_seller_revenue, ad_cost, net_profit, cum_net_profit, orders, settled_orders, provisional_orders}, `events[]` {date, type ad_deduction/video_posted, amount, label}, `gmv_sources[]` (shop_metrics: video / product card / live, gmv_max_pct) |
| `GET /api/analytics/products` | 4 | `rows[]` {product_id, title, units, orders, gmv, net_seller_revenue, fees, affiliate, cogs, ad_cost (estimate), refunds, net_profit, net_margin, cvr, ctr, status SCALE/HEALTHY/WATCH/INVESTIGATE/REDUCE/SMALL_SAMPLE (NO_SALES only inside video-products), status_reason}; cards carry `meta` with structured note values (units, refunded, ad_share, floor, break_even, settled/provisional) |
| `GET /api/analytics/videos` | 4 | `cards[]` {video_id, external_video_id, caption, published_at, duration_seconds, age_days, views, impressions, clicks, orders, gmv, ctr, cvr, gpm, ad_spend=null, net_profit=null, ad_spend_note, classification WINNER/PROMISING/…/INSUFFICIENT_DATA, confidence, reasons[]} |
| `GET /api/analytics/campaigns` | 4 | `available:false`, `reason`, `shop_level_ad_cost`, `deductions[]` — until Ads API |
| `GET /api/analytics/creators` | 4 | `rows[]` one aggregated affiliate row (orders, gmv, affiliate_commission, profit_after_commission) |
| `GET /api/dashboard/funnel` | 5 | `stages[]` impression→click→order→completed→settled, `steps[]` {rate, baseline_rate, delta_pct}, `diagnosis` (largest drop, lost_orders, lost_profit, estimated:true) or null, `waterfall` {steps[] {key, amount, measured, subtotal?}, orders, provisional_orders, note} |
| `GET /api/dashboard/insights` | 2, 6 | `findings[]` {key, kind risk/opportunity, severity CRITICAL/WARNING/OPPORTUNITY/INFO, title, detail, impact, confidence HIGH/MEDIUM/LOW, source, measured, links{tab/product_id/video_id/zone}}, `opportunities[]`, `risks[]` — deterministic rules, no LLM |
| `GET /api/tasks` / `POST /api/tasks` / `PATCH /api/tasks/{id}` | 7 | task {id, title, detail, team performance/video/design/product/finance/management, priority P1-P3, status today/in_progress/review/done, owner, deadline, impact_note, source, evidence, result_note, done_at}; GET also returns `columns` grouped by status |

Labels the UI must keep: ad cost = "BLENDED estimate (LOW)"; provisional orders ≠ settled; reported ROAS / per-campaign / per-video ad cost = NOT AVAILABLE until Ads API. `/health` (no `/api` prefix) reports DB + last sync/job times.

## Dashboard (frontend, `apps/dashboard`)

Next.js 15 App Router, TypeScript, one global stylesheet with the mock's CSS variables (dark mode via `prefers-color-scheme`), no chart libraries (SVG). Client page fetches all endpoints in parallel from `NEXT_PUBLIC_API_BASE` (default `""` = same origin; Caddy proxies `/api/*` to `api:8400`). Filter state lives in the URL: `?preset=month|30d|custom&from=&to=&tab=products|videos|campaigns|creators&shop_id=`. Language (EN/RU) persists in `localStorage["tt-lang"]`.

| Zone | Component | Endpoint |
|---|---|---|
| Header | `Shell.tsx` | `overview.shop/period/compare/data_quality` |
| 1 Business health | `Health.tsx` | `/api/dashboard/overview` (`cards`, `health`, `unit_economics`, `totals`, `notes`) |
| 2 Diagnosis | `Diagnosis.tsx` | `/api/dashboard/insights.findings` (labelled "Deterministic rules · no LLM") |
| 3 Trend | `Trend.tsx` | `/api/dashboard/trends` (`series`, `events`, `gmv_sources`) |
| 4 Explorer | `Explorer.tsx` | `/api/analytics/products`, `/videos`, `/campaigns`, `/creators` |
| 4b Videos → Product cards | `VideoProducts.tsx`, `History.tsx` | `/api/analytics/video-products` (`shop_split`, `dependency`, `products`, `videos`, `history`) |
| 5 Funnel & waterfall | `Funnel.tsx` | `/api/dashboard/funnel` |
| 6 Opportunities & leakage | `Opps.tsx` | `/api/dashboard/insights.opportunities/.risks` |
| 7 Team board | `Board.tsx` | `GET/POST /api/tasks`, `PATCH /api/tasks/{id}` (status buttons; "Create task" prefills from a finding with `evidence={insight: key, ...links}`, `source="insight"`) |

Decimals are parsed with `Number()` only for display; nothing is recomputed client-side. Nulls render as "—" with the API note. Dev without the API: `npm run dev:mock` (fixtures under `apps/dashboard/fixtures/`).
