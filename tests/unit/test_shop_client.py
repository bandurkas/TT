import json
import time

import httpx
import pytest

from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_shop.client import (
    FileTokenProvider,
    ShopApiError,
    StaticTokenProvider,
    TikTokShopClient,
)
from src.integrations.tiktok_shop.signing import compute_sign


def make_client(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TikTokShopClient("KEY", "SECRET", StaticTokenProvider("TOK"), shop_cipher="CIPH",
                            base_url="https://x.test", http=http, sleep=lambda _s: None,
                            now_ms=lambda: 1700000000000, backoff_base=0.01, **kw)


def ok(data, request_id="r1"):
    return httpx.Response(200, json={"code": 0, "message": "Success",
                                     "request_id": request_id, "data": data})


def test_common_params_headers_and_signature():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = req.url, req.headers, req.content
        return ok({"orders": []})

    c = make_client(handler)
    list(c.get_orders(create_time_ge=1, create_time_lt=2))
    q = dict(seen["url"].params)
    assert q["app_key"] == "KEY" and q["shop_cipher"] == "CIPH" and q["timestamp"] == "1700000000"
    assert seen["headers"]["x-tts-access-token"] == "TOK"
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["url"].path == "/order/202309/orders/search"
    body = seen["body"]
    assert json.loads(body) == {"create_time_ge": 1, "create_time_lt": 2}
    expected = compute_sign("SECRET", "/order/202309/orders/search",
                            {k: v for k, v in q.items() if k != "sign"}, body)
    assert q["sign"] == expected


def test_get_request_signs_without_body_and_no_cipher_for_shops():
    seen = {}

    def handler(req):
        seen["q"] = dict(req.url.params)
        return ok({"shops": [{"cipher": "C"}]})

    c = make_client(handler)
    assert c.get_authorized_shops() == [{"cipher": "C"}]
    assert "shop_cipher" not in seen["q"]
    q = {k: v for k, v in seen["q"].items() if k != "sign"}
    assert seen["q"]["sign"] == compute_sign("SECRET", "/authorization/202309/shops", q, None)


def test_retry_on_429_then_success():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"code": 429, "message": "rate"})
        return ok({"products": [{"id": "p1"}]})

    c = make_client(handler)
    assert [p["id"] for p in c.get_products()] == ["p1"]
    assert len(calls) == 3


def test_retry_exhausted_raises():
    def handler(req):
        return httpx.Response(503, json={"code": 503, "message": "down"})

    c = make_client(handler, max_retries=2)
    with pytest.raises(ShopApiError):
        c.get_product("p")


def test_api_error_code_raises():
    def handler(req):
        return httpx.Response(200, json={"code": 105001, "message": "bad", "request_id": "x"})

    with pytest.raises(ShopApiError) as e:
        make_client(handler).get_shop_performance("2026-08-01", "2026-08-02")
    assert e.value.code == 105001


def test_pagination_follows_page_token():
    tokens = []

    def handler(req):
        tokens.append(req.url.params.get("page_token"))
        if len(tokens) == 1:
            return ok({"statements": [{"id": 1}], "next_page_token": "T2"})
        return ok({"statements": [{"id": 2}], "next_page_token": ""})

    rows = list(make_client(handler).get_finance_statements(statement_time_ge=1, page_size=1))
    assert [r["id"] for r in rows] == [1, 2]
    assert tokens == [None, "T2"]


def test_raw_sink_receives_meta_and_payload():
    got = []

    def handler(req):
        return ok({"orders": [{"id": "o1"}]}, request_id="rid")

    c = make_client(handler, raw_sink=lambda r, m, p: got.append((r, m, p)))
    assert c.get_order_detail(["o1"]) == [{"id": "o1"}]
    res, meta, payload = got[0]
    assert res == "order_detail" and meta["request_id"] == "rid" and "sign" not in meta["query"]
    assert payload["code"] == 0 and meta["query"]["ids"] == "o1"


def test_unverified_method_raises():
    with pytest.raises(NotImplementedError, match="UNVERIFIED"):
        make_client(lambda r: ok({})).get_affiliate_orders()


def test_file_token_provider_refreshes_near_expiry(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    now = int(time.time())
    store.save({"access_token": "OLD", "refresh_token": "R",
                "access_token_expire_in": now + 600})
    calls = []

    def handler(req):
        calls.append(req.url.path)
        assert req.url.params["refresh_token"] == "R"
        return httpx.Response(200, json={"code": 0, "data": {
            "access_token": "NEW", "refresh_token": "R2",
            "access_token_expire_in": now + 7 * 86400}})

    p = FileTokenProvider(store, "K", "S", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.get_access_token() == "NEW"
    assert calls == ["/api/v2/token/refresh"]
    assert store.load()["refresh_token"] == "R2"
    assert p.get_access_token() == "NEW" and len(calls) == 1


def test_file_token_provider_no_refresh_when_fresh(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    store.save({"access_token": "A", "refresh_token": "R",
                "access_token_expire_in": int(time.time()) + 86400})
    p = FileTokenProvider(store, "K", "S", http=httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("must not call"))))
    assert p.get_access_token() == "A"
