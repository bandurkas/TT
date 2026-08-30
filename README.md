# TT — TikTok Shop Profit Control AI

Operational AI analyst for a TikTok Shop: pulls Shop/Ads/Finance data, joins it with internal COGS, computes **real profit** (not platform ROAS), classifies videos/campaigns/products, explains changes, and turns findings into team actions (Telegram + dashboard).

Full spec: [docs/SPEC.md](docs/SPEC.md). Working rules: [CLAUDE.md](CLAUDE.md). Status: latest `HANDOFF_*.md`.

## Status
The repository includes Shop/Ads adapters, ingestion jobs, deterministic profit analytics, an APScheduler worker, FastAPI dashboard endpoints and a Next.js dashboard. For verified local setup and remaining blockers, see [development readiness](docs/DEVELOPMENT_READINESS.md). Historical deployment notes in `HANDOFF_*.md` are not a live server status check.

The [order journal](docs/ORDER_JOURNAL.md) shows per-order costs, revenue shares, source evidence and statement reconciliation. Advertising allocation remains an estimate. Access protection is still an open deployment risk.

## Run (local)

Backend requires Python 3.12+ and Linux (the Shop token provider uses `fcntl`). On Windows, use Linux containers/WSL for the backend. To preview the dashboard with fixture data on this prepared Windows checkout:

```powershell
.\scripts\dashboard-mock.ps1
```

Linux backend:
```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
pytest
uvicorn apps.api.main:app --port 8400 --reload
```

## Run (docker)
```
cp .env.example .env   # fill secrets
docker compose up -d --build
curl localhost:8400/health
```

## Layout
See SPEC §24. `src/integrations` (TikTok Shop / Ads / Telegram adapters), `src/domain`, `src/analytics` (deterministic engine), `src/agents` (LLM placeholder), `apps/api`, `apps/worker`, `apps/dashboard` (Next.js).
