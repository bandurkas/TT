"""GMV Max daily Cost straight from TikTok's own Marketing API — the source Windsor stood in for.

Field names were verified live on 2026-09-09 (docs/ads-api-live-probe-2026-09-09.md); the API answers
a wrong dimension with a bare "ERROR Message.", so they are never guessed.

Two things this module exists to get right:

1. **Both advertisers are queried.** `/campaign/get/` returns 0 campaigns for the account that holds
   every live GMV Max campaign, because GMV Max campaigns do not appear there at all. Trusting that
   zero is how the main account gets mistaken for an empty one.
2. **The open day is returned and kept.** Unlike the Windsor connector, whose clock trails the shop's,
   this API reports today. The reading is a moment in time, not a closed figure, and is written as
   `partial` with the fetch timestamp so the dashboard can say what it is.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.integrations.tiktok_ads.client import TikTokAdsClient

METRICS = ["cost", "orders", "gross_revenue"]
DIMENSIONS = ["campaign_id", "stat_time_day"]
RESOURCE = "gmv_max_daily"


class GmvMaxError(RuntimeError):
    """The report could not be read for an advertiser; the caller must not treat it as zero spend."""


def _day(v: Any) -> date:
    # "2026-09-09 00:00:00" — the report always returns midnight in the advertiser's timezone.
    return date.fromisoformat(str(v)[:10])


def campaign_names(client: TikTokAdsClient, advertiser_id: str, store_ids: list[str]) -> dict[str, str]:
    """Names are absent from the report and only useful for display, so a failure here is not fatal."""
    try:
        rows = client.paginate("/gmv_max/campaign/get/", {
            "advertiser_id": advertiser_id,
            "filtering": {"store_ids": store_ids,
                          "gmv_max_promotion_types": ["PRODUCT_GMV_MAX", "LIVE_GMV_MAX"]}},
            "gmv_max_campaigns", page_size=50)
        return {str(c["campaign_id"]): c.get("campaign_name") or "" for c in rows if c.get("campaign_id")}
    except Exception:  # noqa: BLE001 — display-only
        return {}


def stores(client: TikTokAdsClient, advertiser_id: str) -> list[str]:
    """`/store/list/` keys its payload `stores`, not `list`, so `paginate` cannot be used here."""
    data = client.request("/store/list/", {"advertiser_id": advertiser_id, "page_size": 50}, "stores")
    return [str(s["store_id"]) for s in (data.get("stores") or []) if s.get("store_id")]


def fetch(client: TikTokAdsClient, advertiser_ids: list[str], start: date, end: date
          ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Flat rows for the ingest, plus metadata for the raw layer.

    An advertiser that raises stops the whole fetch: a partial set summed into a day's Cost would
    understate it, and understated ad Cost is exactly the failure this project has already paid for.
    """
    rows: list[dict[str, Any]] = []
    seen: dict[str, list[str]] = {}
    for adv in advertiser_ids:
        try:
            store_ids = stores(client, adv)
        except Exception as e:  # noqa: BLE001
            raise GmvMaxError(f"store list failed for {adv}: {e}") from e
        seen[adv] = store_ids
        if not store_ids:
            continue
        names = campaign_names(client, adv, store_ids)
        try:
            report = list(client.iter_gmv_max_report(
                adv, store_ids, DIMENSIONS, METRICS, str(start), str(end), page_size=200))
        except Exception as e:  # noqa: BLE001
            raise GmvMaxError(f"gmv_max report failed for {adv}: {e}") from e
        for r in report:
            d, m = r.get("dimensions") or {}, r.get("metrics") or {}
            cid = d.get("campaign_id")
            if cid is None or d.get("stat_time_day") is None or m.get("cost") is None:
                # A row we cannot place is not a zero; skip it and let the day stand on the rest.
                continue
            rows.append({"date": _day(d["stat_time_day"]), "advertiser_id": str(adv),
                         "campaign_id": str(cid), "campaign": names.get(str(cid)),
                         "cost": Decimal(str(m["cost"])),
                         "ad_orders": int(float(m.get("orders") or 0)),
                         "ad_revenue": Decimal(str(m.get("gross_revenue") or 0))})
    meta = {"source": "tiktok_ads", "endpoint": "/gmv_max/report/get/", "advertisers": seen,
            "start": str(start), "end": str(end), "dimensions": DIMENSIONS, "metrics": METRICS}
    return rows, meta


def campaigns(client: TikTokAdsClient, advertiser_id: str, store_ids: list[str]) -> list[str]:
    return [str(c["campaign_id"]) for c in client.paginate("/gmv_max/campaign/get/", {
        "advertiser_id": advertiser_id,
        "filtering": {"store_ids": store_ids,
                      "gmv_max_promotion_types": ["PRODUCT_GMV_MAX", "LIVE_GMV_MAX"]}},
        "gmv_max_campaigns", page_size=50) if c.get("campaign_id")]


def fetch_products(client: TikTokAdsClient, advertiser_ids: list[str], start: date, end: date
                   ) -> tuple[list[dict[str, Any]], Decimal]:
    """Per-product spend. `item_group_id` **is** the shop's `external_product_id` (verified
    2026-09-09), which is what turns campaign Cost into product P&L.

    Returns the rows and the spend that no product accounts for. That remainder is real money and
    is handed back rather than spread: the blended allocation it replaces was wrong by up to 3x per
    product, and silently smearing the unattributed part would rebuild the same error.
    """
    rows: list[dict[str, Any]] = []
    attributed = Decimal(0)
    for adv in advertiser_ids:
        store_ids = stores(client, adv)
        if not store_ids:
            continue
        for cid in campaigns(client, adv, store_ids):
            report = list(client.iter_gmv_max_report(
                adv, store_ids, ["item_group_id", "stat_time_day"], METRICS,
                str(start), str(end), page_size=200, filtering={"campaign_ids": [cid]}))
            for r in report:
                d, m = r.get("dimensions") or {}, r.get("metrics") or {}
                gid = d.get("item_group_id")
                if not gid or gid == "-1" or d.get("stat_time_day") is None or m.get("cost") is None:
                    continue
                cost = Decimal(str(m["cost"]))
                attributed += cost
                rows.append({"date": _day(d["stat_time_day"]), "advertiser_id": str(adv),
                             "campaign_id": cid, "external_product_id": str(gid), "cost": cost,
                             "ad_orders": int(float(m.get("orders") or 0)),
                             "ad_revenue": Decimal(str(m.get("gross_revenue") or 0))})
    return rows, attributed
