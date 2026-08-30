from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import select, text

from apps.api.oauth import router as oauth_router
from apps.worker.scheduler import STALE_AFTER
from src.config.settings import settings
from src.db.models import IntegrationSyncState
from src.db.session import SessionLocal

app = FastAPI(title="TikTok Shop Profit Control AI", version="0.0.1")
app.include_router(oauth_router)


def sync_summary(session) -> list[dict]:
    rows = session.scalars(select(IntegrationSyncState).order_by(IntegrationSyncState.integration,
                                                                 IntegrationSyncState.resource_type))
    now = datetime.now(UTC)
    out = []
    for s in rows:
        ok, att = s.last_successful_sync, s.last_attempt
        limit = STALE_AFTER.get(s.resource_type.removeprefix("job:"))
        stale = bool(limit) and ((ok is None or now - ok > limit) or
                                 (s.status == "running" and att is not None and now - att > limit))
        out.append({"integration": s.integration, "resource": s.resource_type, "status": s.status,
                    "last_success": ok.isoformat(timespec="seconds") if ok else None,
                    "age_minutes": int((now - ok).total_seconds() // 60) if ok else None,
                    "last_attempt": att.isoformat(timespec="seconds") if att else None,
                    "stale": stale, "error": (s.error or "")[:200] or None})
    return out


@app.get("/health")
def health() -> dict:
    try:
        with SessionLocal() as session:
            session.execute(text("select 1"))
            syncs = sync_summary(session)
        db = "ok"
    except Exception as e:  # noqa: BLE001
        db, syncs = f"error: {type(e).__name__}", []
    jobs = [s for s in syncs if s["resource"].startswith("job:")]
    degraded = db != "ok" or any(s["status"] == "error" or s["stale"] for s in syncs)
    return {"status": "degraded" if degraded else "ok", "env": settings.app_env, "db": db,
            "jobs": jobs, "syncs": [s for s in syncs if not s["resource"].startswith("job:")]}


@app.get("/ready")
def ready() -> dict:
    with SessionLocal() as session:
        session.execute(text("select 1"))
    return {"status": "ready"}
