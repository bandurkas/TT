import hashlib
import hmac

from src.integrations.tiktok_shop.signing import compute_sign, normalise_query, sign_string

SECRET = "secret123"
PATH = "/order/202309/orders/search"
QUERY = {"timestamp": 1700000000, "app_key": "abc", "shop_cipher": "XYZ", "page_size": 10,
         "sign": "ignored", "access_token": "ignored"}
BODY = b'{"order_status":"COMPLETED"}'


def test_sign_string_layout():
    assert sign_string(SECRET, PATH, QUERY, BODY) == (
        "secret123/order/202309/orders/search"
        "app_keyabcpage_size10shop_cipherXYZtimestamp1700000000"
        '{"order_status":"COMPLETED"}secret123')


def test_fixed_vector():
    # self-generated, UNVERIFIED — replace with official vector in Deliverable 5
    assert compute_sign(SECRET, PATH, QUERY, BODY) == "d4e1f549555a93abdb481fc6ececcf540380c793456505d54f497a5ac06d5a77"


def test_matches_reference_hmac_without_body():
    msg = b"secret123/authorization/202309/shopsapp_keyabctimestamp1secret123"
    ref = hmac.new(b"secret123", msg, hashlib.sha256).hexdigest()
    assert compute_sign(SECRET, "/authorization/202309/shops",
                        {"app_key": "abc", "timestamp": 1}) == ref
    assert len(ref) == 64 and ref == ref.lower()


def test_normalise_query_bool_list_none():
    assert normalise_query({"a": True, "b": False, "c": [1, "x"], "d": None, "e": 5}) == {
        "a": "true", "b": "false", "c": "1,x", "e": "5"}
