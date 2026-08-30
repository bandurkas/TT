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
