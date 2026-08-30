"""TikTok Shop OAuth: auth_code -> tokens, refresh. Endpoints per Partner Center
authorization docs (auth.tiktok-shops.com/api/v2/token/{get,refresh})."""
import json
import time
from pathlib import Path

import httpx

AUTH_BASE = "https://auth.tiktok-shops.com/api/v2"


class ShopAuthError(RuntimeError):
    pass


def _check(resp: httpx.Response) -> dict:
    body = resp.json()
    if resp.status_code != 200 or body.get("code") != 0:
        raise ShopAuthError(f"code={body.get('code')} message={body.get('message')}")
    return body["data"]


def exchange_code(app_key: str, app_secret: str, auth_code: str, client: httpx.Client | None = None) -> dict:
    c = client or httpx.Client(timeout=20)
    r = c.get(f"{AUTH_BASE}/token/get", params={
        "app_key": app_key, "app_secret": app_secret,
        "auth_code": auth_code, "grant_type": "authorized_code",
    })
    return _check(r)


def refresh_token(app_key: str, app_secret: str, refresh: str, client: httpx.Client | None = None) -> dict:
    c = client or httpx.Client(timeout=20)
    r = c.get(f"{AUTH_BASE}/token/refresh", params={
        "app_key": app_key, "app_secret": app_secret,
        "refresh_token": refresh, "grant_type": "refresh_token",
    })
    return _check(r)


class TokenStore:
    """Phase 0 file store. TODO Phase 1: encrypted DB row per shop."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {**data, "saved_at": int(time.time())}
        self.path.write_text(json.dumps(data, indent=2))
        self.path.chmod(0o600)

    def load(self) -> dict | None:
        return json.loads(self.path.read_text()) if self.path.exists() else None

    def public_view(self) -> dict | None:
        d = self.load()
        if not d:
            return None
        return {k: v for k, v in d.items() if "token" not in k} | {
            "has_access_token": bool(d.get("access_token")),
            "has_refresh_token": bool(d.get("refresh_token")),
        }
