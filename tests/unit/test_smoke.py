from fastapi.testclient import TestClient

from apps.api.main import app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_shop_callback_captures_code():
    r = TestClient(app).get("/oauth/tiktok-shop/callback?code=abc&state=x")
    assert r.status_code == 200
    assert r.json()["received"] is True
