# TT — TikTok Shop Profit Control AI

Operational AI analyst for a TikTok Shop: pulls Shop/Ads/Finance data, joins it with internal COGS, computes **real profit** (not platform ROAS), classifies videos/campaigns/products, explains changes, and turns findings into team actions (Telegram + dashboard).

Full spec: [docs/SPEC.md](docs/SPEC.md). Working rules: [CLAUDE.md](CLAUDE.md). Status: latest `HANDOFF_*.md`.

## Status
Phase 0 — API validation. Skeleton only; no TikTok adapters yet.

## Run (local)
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
See SPEC §24. `src/integrations` (TikTok Shop / Ads / Telegram adapters), `src/domain`, `src/analytics` (deterministic engine), `src/agents` (LLM layer), `apps/api`, `apps/worker`, `apps/dashboard` (Next.js, later).
