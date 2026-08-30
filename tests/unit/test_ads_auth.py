import httpx

from apps.api import oauth
from src.integrations.tiktok_ads.auth import AdsAuthError, exchange_auth_code


def _client(status, body):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))


def test_exchange_ok():
    d = exchange_auth_code("id", "s", "code", _client(200, {"code": 0, "data": {"access_token": "t", "advertiser_ids": ["1"]}}))
    assert d["advertiser_ids"] == ["1"]


def test_exchange_error():
    try:
        exchange_auth_code("id", "s", "bad", _client(200, {"code": 40002, "message": "invalid auth_code"}))
        raise AssertionError
    except AdsAuthError as e:
        assert e.code == 40002


def test_ads_callback_success(monkeypatch, tmp_path, caplog):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from src.integrations.tiktok_shop.auth import TokenStore
    monkeypatch.setattr(oauth.settings, "tiktok_ads_app_id", "id")
    monkeypatch.setattr(oauth, "ads_store", TokenStore(tmp_path / "ads.json"))
    monkeypatch.setattr(oauth, "exchange_auth_code", lambda *a, **k: {"access_token": "T", "advertiser_ids": ["77"], "scope": [4]})
    r = TestClient(app).get("/oauth/tiktok-ads/callback?auth_code=SECRETCODE")
    assert r.json()["ok"] is True and r.json()["advertiser_ids"] == ["77"]
    assert "SECRETCODE" not in caplog.text
    assert oauth.ads_store.public_view()["has_access_token"]
