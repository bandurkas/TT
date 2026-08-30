"""TikTok Business (Marketing) API v1.3 client, read-only. Paths from the official SDK
github.com/tiktok/tiktok-business-api-sdk (python_sdk/docs/*.md)."""
import json
import logging
import random
import time
from collections.abc import Callable, Iterator, Mapping
from typing import Any

import httpx

log = logging.getLogger("tt.ads")
BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RawSink = Callable[[str, dict[str, Any], dict[str, Any]], None]


class AdsApiError(RuntimeError):
    def __init__(self, code: object, message: object, request_id: object = None):
        super().__init__(f"code={code} message={message} request_id={request_id}")
        self.code, self.message, self.request_id = code, message, request_id


def _encode(params: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in params.items():
        if v is None:
            continue
        out[k] = json.dumps(v, separators=(",", ":")) if isinstance(v, (list, dict)) else str(v)
    return out


class TikTokAdsClient:
    def __init__(self, access_token: str, base_url: str = BASE_URL,
                 raw_sink: RawSink | None = None, http: httpx.Client | None = None,
                 max_retries: int = 4, backoff_base: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep):
        self.access_token, self.base_url, self.raw_sink = access_token, base_url.rstrip("/"), raw_sink
        self.http = http or httpx.Client(timeout=60)
        self.max_retries, self.backoff_base, self.sleep = max_retries, backoff_base, sleep

    def request(self, path: str, params: Mapping[str, Any], resource: str = "") -> dict[str, Any]:
        q = _encode(params)
        headers = {"Access-Token": self.access_token}
        url = self.base_url + path
        for attempt in range(self.max_retries + 1):
            resp = self.http.get(url, params=q, headers=headers)
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                delay = self.backoff_base * 2 ** attempt * (1 + random.random() * 0.1)
                log.warning("ads GET %s -> %s, retry in %.2fs", path, resp.status_code, delay)
                self.sleep(delay)
                continue
            break
        payload = resp.json()
        meta = {"method": "GET", "path": path, "query": q, "status": resp.status_code,
                "request_id": payload.get("request_id")}
        if self.raw_sink:
            self.raw_sink(resource or path, meta, payload)
        if resp.status_code != 200 or payload.get("code") != 0:
            raise AdsApiError(payload.get("code", resp.status_code), payload.get("message"),
                              payload.get("request_id"))
        return payload.get("data") or {}

    def paginate(self, path: str, params: Mapping[str, Any], resource: str = "",
                 page_size: int = 100) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            data = self.request(path, {**params, "page": page, "page_size": page_size}, resource)
            yield from data.get("list") or []
            info = data.get("page_info") or {}
            if page >= int(info.get("total_page") or 1):
                return
            page += 1

    def get_advertiser_info(self, advertiser_ids: list[str],
                            fields: list[str] | None = None) -> list[dict[str, Any]]:
        data = self.request("/advertiser/info/", {"advertiser_ids": advertiser_ids,
                                                  "fields": fields}, "advertiser_info")
        return data.get("list") or []

    def _objects(self, path: str, advertiser_id: str, filtering: Mapping[str, Any] | None,
                 fields: list[str] | None, resource: str) -> Iterator[dict[str, Any]]:
        return self.paginate(path, {"advertiser_id": advertiser_id, "filtering": filtering,
                                    "fields": fields}, resource)

    def get_campaigns(self, advertiser_id: str, filtering: Mapping[str, Any] | None = None,
                      fields: list[str] | None = None) -> Iterator[dict[str, Any]]:
        return self._objects("/campaign/get/", advertiser_id, filtering, fields, "campaigns")

    def get_adgroups(self, advertiser_id: str, filtering: Mapping[str, Any] | None = None,
                     fields: list[str] | None = None) -> Iterator[dict[str, Any]]:
        return self._objects("/adgroup/get/", advertiser_id, filtering, fields, "adgroups")

    def get_ads(self, advertiser_id: str, filtering: Mapping[str, Any] | None = None,
                fields: list[str] | None = None) -> Iterator[dict[str, Any]]:
        return self._objects("/ad/get/", advertiser_id, filtering, fields, "ads")

    def get_creatives(self, advertiser_id: str, filtering: Mapping[str, Any] | None = None
                      ) -> Iterator[dict[str, Any]]:
        # Video assets via /file/video/ad/search/ (SDK FileApi). Mapping ad -> video_id comes
        # from ad/get `video_id` field  # UNVERIFIED
        return self.paginate("/file/video/ad/search/", {"advertiser_id": advertiser_id,
                                                        "filtering": filtering}, "creatives",
                             page_size=100)

    def get_video_info(self, advertiser_id: str, video_ids: list[str]) -> list[dict[str, Any]]:
        data = self.request("/file/video/ad/info/", {"advertiser_id": advertiser_id,
                                                     "video_ids": video_ids[:60]}, "video_info")
        return data.get("list") or []

    def get_report(self, advertiser_id: str, level: str, dimensions: list[str],
                   metrics: list[str], start: str, end: str, page: int = 1, page_size: int = 100,
                   report_type: str = "BASIC", service_type: str = "AUCTION",
                   filtering: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        """Synchronous report: GET /report/integrated/get/. level = AUCTION_CAMPAIGN |
        AUCTION_ADGROUP | AUCTION_AD (data_level values  # UNVERIFIED)."""
        return self.request("/report/integrated/get/", {
            "advertiser_id": advertiser_id, "service_type": service_type,
            "report_type": report_type, "data_level": level, "dimensions": dimensions,
            "metrics": metrics, "start_date": start, "end_date": end, "filtering": filtering,
            "page": page, "page_size": page_size}, "report")

    def iter_report(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            data = self.get_report(*args, page=page, **kwargs)
            yield from data.get("list") or []
            if page >= int((data.get("page_info") or {}).get("total_page") or 1):
                return
            page += 1

    def get_gmv_max_report(self, advertiser_id: str, store_ids: list[str], dimensions: list[str],
                           metrics: list[str], start: str, end: str, page: int = 1,
                           page_size: int = 100, filtering: Mapping[str, Any] | None = None
                           ) -> dict[str, Any]:
        # GET /gmv_max/report/get/ per SDK ReportingApi.md; doc portal page
        # gmv-max-ads-reports/v1.3 also describes report/integrated/get with report_type=TT_SHOP.
        # Metrics/dimensions names  # UNVERIFIED
        return self.request("/gmv_max/report/get/", {
            "advertiser_id": advertiser_id, "store_ids": store_ids, "dimensions": dimensions,
            "metrics": metrics, "start_date": start, "end_date": end, "filtering": filtering,
            "page": page, "page_size": page_size}, "gmv_max_report")
