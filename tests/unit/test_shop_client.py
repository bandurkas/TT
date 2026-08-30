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
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, json={"code": 503, "message": "down"})

    c = make_client(handler, max_retries=2)
    with pytest.raises(ShopApiError) as e:
        c.get_product("p")
    assert len(calls) == 3 and e.value.status == 503


def test_retry_after_header_on_429_capped():
    calls, slept = [], []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "90"}, json={"code": 429})
        return ok({})

    c = make_client(handler)
    c.sleep = slept.append
    c.get_product("p")
    assert slept == [30.0]


def test_transport_error_retried_then_raises():
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ShopApiError) as e:
        make_client(handler, max_retries=1).get_product("p")
    assert len(calls) == 2 and e.value.code == "transport"


def test_non_json_502_raw_sink_once_then_error():
    got = []
    c = make_client(lambda r: httpx.Response(502, text="<html>bad gateway</html>"),
                    raw_sink=lambda r, m, p: got.append(p), max_retries=0)
    with pytest.raises(ShopApiError) as e:
        c.get_product("p")
    assert len(got) == 1 and got[0]["_non_json"] is True and got[0]["status"] == 502
    assert e.value.status == 502 and e.value.code == 502 and "bad gateway" in e.value.message


def test_error_code_falls_back_to_status():
    with pytest.raises(ShopApiError) as e:
        make_client(lambda r: httpx.Response(403, json={"message": "forbidden"}),
                    max_retries=0).get_product("p")
    assert e.value.code == 403 and e.value.status == 403


def test_bool_query_sent_equals_signed():
    seen = {}

    def handler(req):
        seen["q"] = dict(req.url.params)
        return ok({})

    make_client(handler).request("GET", "/x", query={"flag": True, "ids": ["a", "b"]})
    q = seen["q"]
    assert q["flag"] == "true" and q["ids"] == "a,b"
    assert q["sign"] == compute_sign("SECRET", "/x", {k: v for k, v in q.items() if k != "sign"})


def test_pagination_loop_detected():
    def handler(req):
        return ok({"products": [{"id": "p"}], "next_page_token": "SAME"})

    with pytest.raises(ShopApiError, match="pagination_loop"):
        list(make_client(handler).get_products())


def test_pagination_max_pages_cap():
    n = [0]

    def handler(req):
        n[0] += 1
        return ok({"products": [], "next_page_token": f"T{n[0]}"})

    with pytest.raises(ShopApiError, match="max_pages"):
        list(make_client(handler, max_pages=3).get_products())
    assert n[0] == 3


def test_default_redactor_strips_order_pii():
    got = []

    def handler(req):
        return ok({"orders": [{"id": "o1", "recipient_address": {"x": 1}, "buyer_email": "e",
                               "line_items": [{"sku": "s", "phone": "p"}]}]})

    c = make_client(handler, raw_sink=lambda r, m, p: got.append(p))
    rows = list(c.get_orders())
    assert rows[0]["buyer_email"] == "e"  # caller still gets full data
    o = got[0]["data"]["orders"][0]
    assert o == {"id": "o1", "line_items": [{"sku": "s"}]}


def test_redact_none_passes_payload_through():
    got = []
    c = make_client(lambda r: ok({"orders": [{"buyer_email": "e"}]}),
                    raw_sink=lambda r, m, p: got.append(p), redact=None)
    list(c.get_orders())
    assert got[0]["data"]["orders"][0]["buyer_email"] == "e"


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


def test_file_token_provider_missing_expiry_refreshes(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    store.save({"access_token": "OLD", "refresh_token": "R"})
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={"code": 0, "data": {
            "access_token": "NEW", "refresh_token": "R2", "access_token_expire_in": 2_000_000}})

    p = FileTokenProvider(store, "K", "S", now=lambda: 1_000_000,
                          http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.get_access_token() == "NEW" and calls == [1]


def test_file_token_provider_double_check_under_lock(tmp_path):
    """Token looks expired on first read; another process refreshes before we take the lock."""
    store = TokenStore(tmp_path / "t.json")
    store.save({"access_token": "OLD", "refresh_token": "R", "access_token_expire_in": 1_000_100})
    p = FileTokenProvider(store, "K", "S", now=lambda: 1_000_000, http=httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("must not refresh"))))
    orig_load, loads = store.load, []

    def load():
        loads.append(1)
        if len(loads) == 2:  # the re-read under the lock sees a fresh token
            store.save({"access_token": "FRESH", "refresh_token": "R2",
                        "access_token_expire_in": 1_000_000 + 7 * 86400})
        return orig_load()

    store.load = load
    assert p.get_access_token() == "FRESH"
    assert p.lock_path.exists()


def test_file_token_provider_force_refresh(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    store.save({"access_token": "A", "refresh_token": "R", "access_token_expire_in": 9_000_000})
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={"code": 0, "data": {"access_token": "B"}})

    p = FileTokenProvider(store, "K", "S", now=lambda: 1_000_000,
                          http=httpx.Client(transport=httpx.MockTransport(handler)))
    p.refresh()
    assert calls == [] and store.load()["access_token"] == "A"
    p.refresh(force=True)
    assert calls == [1] and store.load()["access_token"] == "B"
