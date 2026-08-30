import logging

from fastapi.testclient import TestClient

from apps.api import oauth
from apps.api.main import app
from src.integrations.tiktok_shop.auth import ShopAuthError, TokenStore


def _setup(monkeypatch, tmp_path, exchange):
    monkeypatch.setattr(oauth.settings, "tiktok_shop_app_key", "K")
    monkeypatch.setattr(oauth.settings, "tiktok_shop_app_secret", "S")
    monkeypatch.setattr(oauth, "shop_store", TokenStore(tmp_path / "t.json"))
    monkeypatch.setattr(oauth, "exchange_code", exchange)
    return TestClient(app)


def test_shop_callback_success(monkeypatch, tmp_path, caplog):
    seen = {}

    def fake(key, secret, code):
        seen.update(key=key, code=code)
        return {"access_token": "a", "refresh_token": "r", "seller_name": "Toko",
                "access_token_expire_in": 123}

    caplog.set_level(logging.INFO)
    r = _setup(monkeypatch, tmp_path, fake).get(
        "/oauth/tiktok-shop/callback?code=SECRETCODE&state=st")
    assert r.json() == {"ok": True, "seller_name": "Toko", "access_token_expire_in": 123,
                        "note": "tokens stored; you can close this tab"}
    assert seen == {"key": "K", "code": "SECRETCODE"}
    assert oauth.shop_store.load()["access_token"] == "a"
    assert "SECRETCODE" not in caplog.text


def test_shop_callback_auth_error_generic(monkeypatch, tmp_path, caplog):
    def fake(*a):
        raise ShopAuthError(36004001, "invalid code", 200)

    caplog.set_level(logging.INFO)
    r = _setup(monkeypatch, tmp_path, fake).get("/oauth/tiktok-shop/callback?code=SECRETCODE")
    assert r.json() == {"ok": False, "error": "token exchange failed"}
    assert "36004001" in caplog.text and "SECRETCODE" not in caplog.text


def test_shop_callback_unexpected_error_generic(monkeypatch, tmp_path, caplog):
    def fake(*a):
        raise RuntimeError("leaky SECRETCODE detail")

    caplog.set_level(logging.INFO)
    r = _setup(monkeypatch, tmp_path, fake).get("/oauth/tiktok-shop/callback?code=SECRETCODE")
    assert r.json() == {"ok": False, "error": "token exchange failed"}
    assert "RuntimeError" in caplog.text and "SECRETCODE" not in caplog.text


def test_ads_callback_never_logs_code(caplog):
    caplog.set_level(logging.INFO)
    r = TestClient(app).get("/oauth/tiktok-ads/callback?auth_code=SECRETCODE")
    assert r.json()["ok"] is False and "SECRETCODE" not in caplog.text  # app id not configured
