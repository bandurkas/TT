"""TikTok Shop OAuth: auth_code -> tokens, refresh. Endpoints per Partner Center
authorization docs (auth.tiktok-shops.com/api/v2/token/{get,refresh})."""
import json
import os
import time
from pathlib import Path

import httpx

AUTH_BASE = "https://auth.tiktok-shops.com/api/v2"


class ShopAuthError(RuntimeError):
    def __init__(self, code: object, message: object, status: int | None = None):
        super().__init__(f"code={code} message={message} status={status}")
        self.code, self.message, self.status = code, message, status


def _check(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise ShopAuthError("non_json", resp.text[:4000], resp.status_code)
    if resp.status_code != 200 or body.get("code") != 0:
        raise ShopAuthError(body.get("code", resp.status_code), body.get("message"),
                            resp.status_code)
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
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # 0600 from creation
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(data, indent=2))
            os.replace(tmp, self.path)  # atomic swap
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

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
