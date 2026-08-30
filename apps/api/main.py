from fastapi import FastAPI

from apps.api.oauth import router as oauth_router
from src.config.settings import settings

app = FastAPI(title="TikTok Shop Profit Control AI", version="0.0.1")
app.include_router(oauth_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@app.get("/ready")
def ready() -> dict:
    # TODO: check DB + Redis connectivity once Phase 1 lands
    return {"status": "ready"}
