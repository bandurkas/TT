from fastapi.testclient import TestClient

from apps.api.main import app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_shop_callback_no_code():
    r = TestClient(app).get("/oauth/tiktok-shop/callback?state=x")
    assert r.status_code == 200
    assert r.json()["ok"] is False
