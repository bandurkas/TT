# TT Dashboard (Next.js 15, App Router)

Read-only profit dashboard for TikTok Shop Profit Control. Reproduces the approved mock (`docs/dashboard-mock.html`): 7 zones + "Videos → Product cards", EN/RU, light/dark via `prefers-color-scheme`. No chart libs — SVG hand-rolled. No auth.

## Run
```
cd apps/dashboard
npm ci
NEXT_PUBLIC_API_BASE=http://localhost:8400 npm run dev   # against a local API (port 3400)
npm run dev:mock                                          # MOCK=1: fixtures/*.json served from /api/* by a Next route handler
npm run build && npm start                                # production (standalone output)
npm run typecheck && npm run lint
```
`NEXT_PUBLIC_API_BASE` is baked in at build time; default `""` = same origin (`/api/...`, proxied by Caddy to `api:8400`).

## Deploy (VPS3, `/root/TT`)
```
git pull && docker compose build dashboard && docker compose up -d --force-recreate dashboard caddy
```
`docker-compose.yml` has the `dashboard` service (node:22-alpine multi-stage, port 3400); Caddy routes `/api/*`, `/oauth/*`, `/health` → `api:8400`, everything else → `dashboard:3400`.

## Structure
```
src/app/layout.tsx           fonts + globals.css (mock CSS variables, dark mode)
src/app/page.tsx             client page: URL state → 10 parallel fetches → zones
src/app/api/[...path]/route.ts  MOCK=1 fixture server (+ in-memory tasks POST/PATCH); 404 otherwise
src/lib/types.ts             API shapes (mirror apps/api/dashboard.py; Decimals = strings)
src/lib/api.ts               fetch helpers, useApi hook, createTask/patchTask
src/lib/format.ts            Rp 1.87m / Rp 254k / Rp 25,000, percentages, dates (Number() only for display)
src/lib/i18n.ts              EN keys → RU map (mock strings reused), LangContext
src/lib/period.ts            ?preset=month|30d|custom&from&to&tab&shop_id → API query
src/components/Shell.tsx     rail + header (period picker, compare, last sync, data-quality badge, Refresh, EN/RU)
src/components/Health.tsx    zone 1  /api/dashboard/overview
src/components/Diagnosis.tsx zone 2  /api/dashboard/insights (findings → Create task)
src/components/Trend.tsx     zone 3  /api/dashboard/trends (SVG: GMV bars, ad bars, cum. net profit, ◆ events)
src/components/Explorer.tsx  zone 4  /api/analytics/{products,videos,campaigns,creators}
src/components/VideoProducts.tsx + History.tsx  zone 4b /api/analytics/video-products (split, lags, matrix, history/lifts/lifecycle)
src/components/Funnel.tsx    zone 5  /api/dashboard/funnel (+ waterfall)
src/components/Opps.tsx      zone 6  insights.opportunities / risks
src/components/Board.tsx     zone 7  /api/tasks (GET/POST/PATCH), create form prefilled from findings
fixtures/*.json              mock payloads (August 2026 numbers from the mock)
```
Honesty labels are rendered from the API notes and fixed strings: ad cost "BLENDED estimate · LOW confidence", settled vs provisional counts, "NOT AVAILABLE — Ads API pending" for reported ROAS / per-campaign / per-video ad cost, video clicks "derived (views × CTR)", funnel stage notes, lift = association not attribution. Null values render as "—".
