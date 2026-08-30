import json

import httpx
import pytest

from src.integrations.tiktok_ads.client import AdsApiError, TikTokAdsClient


def make(handler, **kw):
    return TikTokAdsClient("TOKEN", http=httpx.Client(transport=httpx.MockTransport(handler)),
                           sleep=lambda _s: None, backoff_base=0.01, **kw)


def ok(data):
    return httpx.Response(200, json={"code": 0, "message": "OK", "request_id": "r", "data": data})


def test_header_and_json_encoded_lists():
    seen = {}

    def handler(req):
        seen["h"], seen["q"], seen["path"] = req.headers, dict(req.url.params), req.url.path
        return ok({"list": [{"stat": 1}], "page_info": {"page": 1, "total_page": 1}})

    c = make(handler)
    data = c.get_report("123", "AUCTION_AD", ["ad_id", "stat_time_day"], ["spend"],
                        "2026-08-01", "2026-08-02")
    assert seen["h"]["Access-Token"] == "TOKEN"
    assert seen["path"] == "/open_api/v1.3/report/integrated/get/"
    assert json.loads(seen["q"]["dimensions"]) == ["ad_id", "stat_time_day"]
    assert seen["q"]["data_level"] == "AUCTION_AD" and seen["q"]["report_type"] == "BASIC"
    assert data["list"] == [{"stat": 1}]


def test_pagination_by_total_page():
    pages = []

    def handler(req):
        pages.append(req.url.params["page"])
        return ok({"list": [{"campaign_id": pages[-1]}],
                   "page_info": {"page": int(pages[-1]), "total_page": 2}})

    rows = list(make(handler).get_campaigns("123"))
    assert [r["campaign_id"] for r in rows] == ["1", "2"]
    assert pages == ["1", "2"]


def test_retry_on_500_and_raw_sink():
    calls, got = [], []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(500, json={"code": 50000, "message": "err"})
        return ok({"list": [{"advertiser_id": "1"}]})

    c = make(handler, raw_sink=lambda r, m, p: got.append(r))
    assert c.get_advertiser_info(["1"]) == [{"advertiser_id": "1"}]
    assert len(calls) == 2 and got == ["advertiser_info"]


def test_bool_encoded_lowercase():
    seen = {}

    def handler(req):
        seen["q"] = dict(req.url.params)
        return ok({"list": [], "page_info": {"total_page": 1}})

    list(make(handler).paginate("/x/", {"flag": True, "off": False}))
    assert seen["q"]["flag"] == "true" and seen["q"]["off"] == "false"


def test_non_json_502_raw_sink_then_error():
    got = []
    c = make(lambda r: httpx.Response(502, text="<html>oops</html>"),
             raw_sink=lambda r, m, p: got.append(p), max_retries=0)
    with pytest.raises(AdsApiError) as e:
        c.get_advertiser_info(["1"])
    assert len(got) == 1 and got[0]["_non_json"] and got[0]["status"] == 502
    assert e.value.status == 502 and e.value.code == 502


def test_retry_exhausted_call_count():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, json={"code": 503, "message": "down"})

    with pytest.raises(AdsApiError):
        make(handler, max_retries=2).get_advertiser_info(["1"])
    assert len(calls) == 3


def test_retry_after_header_capped():
    calls, slept = [], []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "120"}, json={"code": 429})
        return ok({"list": []})

    c = TikTokAdsClient("T", http=httpx.Client(transport=httpx.MockTransport(handler)),
                        sleep=slept.append)
    c.get_advertiser_info(["1"])
    assert slept == [30.0]


def test_transport_error_retried():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("boom")
        return ok({"list": [{"advertiser_id": "1"}]})

    assert make(handler).get_advertiser_info(["1"]) == [{"advertiser_id": "1"}]
    assert len(calls) == 2


def test_pagination_max_pages_cap():
    def handler(req):
        return ok({"list": [{"i": 1}], "page_info": {"total_page": 10_000}})

    with pytest.raises(AdsApiError, match="max_pages"):
        list(make(handler, max_pages=3).get_campaigns("1"))


def test_video_info_batched_by_60():
    batches = []

    def handler(req):
        batches.append(len(json.loads(req.url.params["video_ids"])))
        return ok({"list": [{"n": batches[-1]}]})

    rows = make(handler).get_video_info("1", [str(i) for i in range(130)])
    assert batches == [60, 60, 10] and len(rows) == 3


def test_error_code_raises():
    def handler(req):
        return httpx.Response(200, json={"code": 40105, "message": "token", "request_id": "x"})

    with pytest.raises(AdsApiError):
        list(make(handler).get_ads("1"))


def test_gmv_max_report_path():
    seen = {}

    def handler(req):
        seen["path"], seen["q"] = req.url.path, dict(req.url.params)
        return ok({"list": []})

    make(handler).get_gmv_max_report("1", ["s1"], ["stat_time_day"], ["cost"], "2026-08-01",
                                     "2026-08-02")
    assert seen["path"] == "/open_api/v1.3/gmv_max/report/get/"
    assert json.loads(seen["q"]["store_ids"]) == ["s1"]
