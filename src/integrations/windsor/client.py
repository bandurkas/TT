"""Windsor.ai TikTok connector — GMV Max daily Cost, read-only.

The connector answers an unknown field name with `{"data": []}` and HTTP 200, so an empty result is
never evidence of zero spend. Every response is validated against the requested field set before a
caller is allowed to treat it as data.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

BASE = "https://connectors.windsor.ai/tiktok"
# Only fields this advertiser actually populates. Anything else comes back null and would silently
# widen the contract; see docs/windsor-ingest.md §1.
FIELDS = ("date", "account_id", "account_name", "campaign_id", "campaign",
          "gmv_max_ads_spend", "gmv_max_ads_billed_cost")
REQUIRED = ("date", "campaign_id", "gmv_max_ads_spend")


class WindsorError(RuntimeError):
    """The connector refused the request or answered something we must not read as data."""


class WindsorClient:
    def __init__(self, api_key: str, timeout: int = 60, opener: Any = None):
        if not api_key:
            raise WindsorError("Windsor API key is not configured")
        self.api_key, self.timeout = api_key, timeout
        self._open = opener or (lambda url, t: urllib.request.urlopen(url, timeout=t).read())

    def _url(self, start: date, end: date) -> str:
        q = urllib.parse.urlencode({"date_from": str(start), "date_to": str(end),
                                    "fields": ",".join(FIELDS), "api_key": self.api_key})
        return f"{BASE}?{q}"

    @staticmethod
    def redact(url: str) -> str:
        return url.split("&api_key=")[0] + "&api_key=***"

    def fetch_gmv_max(self, start: date, end: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Rows plus request metadata for the raw layer. Raises WindsorError on anything ambiguous."""
        if start > end:
            raise WindsorError(f"Empty range: {start} > {end}")
        url = self._url(start, end)
        try:
            body = self._open(url, self.timeout)
        except Exception as e:  # network, HTTP error, timeout
            raise WindsorError(f"Windsor request failed: {e}") from e
        try:
            doc = json.loads(body)
        except ValueError as e:
            raise WindsorError("Windsor returned a non-JSON body") from e
        if isinstance(doc, dict) and doc.get("error"):
            raise WindsorError(str(doc["error"]))
        rows = doc.get("data") if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            raise WindsorError("Windsor response has no 'data' list")
        for r in rows:
            missing = [k for k in REQUIRED if k not in r]
            if missing:
                # A renamed or dropped field would otherwise read as "no spend".
                raise WindsorError(f"Windsor rows are missing {missing}; refusing to treat as data")
        meta = {"url": self.redact(url), "fields": list(FIELDS),
                "date_from": str(start), "date_to": str(end), "rows": len(rows)}
        return rows, meta
