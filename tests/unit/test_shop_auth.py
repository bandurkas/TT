import os
import stat

import httpx
import pytest

from src.integrations.tiktok_shop.auth import ShopAuthError, TokenStore, exchange_code


def _client(status, body):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))


def test_exchange_ok():
    c = _client(200, {"code": 0, "data": {"access_token": "a", "refresh_token": "r", "seller_name": "s"}})
    assert exchange_code("k", "s", "code", c)["seller_name"] == "s"


def test_exchange_error():
    c = _client(200, {"code": 36004001, "message": "invalid code"})
    try:
        exchange_code("k", "s", "bad", c)
        assert False
    except ShopAuthError as e:
        assert "36004001" in str(e)


def test_store_roundtrip(tmp_path):
    st = TokenStore(tmp_path / "t.json")
    st.save({"access_token": "a", "refresh_token": "r", "seller_name": "s"})
    assert st.load()["access_token"] == "a"
    pv = st.public_view()
    assert pv["has_access_token"] and "access_token" not in pv


def test_exchange_non_json_raises_with_status():
    c = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(502, text="<html>bad gateway</html>")))
    with pytest.raises(ShopAuthError) as e:
        exchange_code("k", "s", "code", c)
    assert e.value.status == 502 and e.value.code == "non_json" and "bad gateway" in e.value.message


def test_store_save_mode_and_atomic(tmp_path):
    st = TokenStore(tmp_path / "sub" / "t.json")
    st.save({"access_token": "a"})
    assert stat.S_IMODE(os.stat(st.path).st_mode) == 0o600
    st.save({"access_token": "b"})  # overwrite via os.replace
    assert st.load()["access_token"] == "b"
    assert stat.S_IMODE(os.stat(st.path).st_mode) == 0o600
    assert [p.name for p in st.path.parent.iterdir()] == ["t.json"]  # no tmp left behind
