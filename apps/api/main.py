from fastapi import FastAPI

from src.config.settings import settings

app = FastAPI(title="TikTok Shop Profit Control AI", version="0.0.1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@app.get("/ready")
def ready() -> dict:
    # TODO: check DB + Redis connectivity once Phase 1 lands
    return {"status": "ready"}
