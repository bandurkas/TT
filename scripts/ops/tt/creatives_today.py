import datetime as dt
from datetime import date
from src.config.settings import settings
from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_ads.client import TikTokAdsClient
from src.integrations.tiktok_ads import gmv_max
tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load()
c = TikTokAdsClient(tok["access_token"])
J = dt.timezone(dt.timedelta(hours=7))
print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"), "Jakarta")
CID, PID = "1876288311852242", "1736665360313713735"
OFF = {"7680398308262661397": "abuabu/aloozeee", "7687447173411278100": "#fyp/aloozeee", "7692323613524921608": "snack/lomira"}
KEEP = {"7680533196836064533": "tahanlama", "7682454426233097490": "cobain", "7688041244991278356": "promo gacor", "7688205494816656661": "approve warga"}
M = ["cost", "orders", "gross_revenue"]
for adv in [str(a) for a in tok["advertiser_ids"]]:
    stores = gmv_max.stores(c, adv)
    if not stores: continue
    for r in c.paginate("/gmv_max/campaign/get/", {"advertiser_id": adv, "filtering": {"store_ids": stores, "gmv_max_promotion_types": ["PRODUCT_GMV_MAX"]}}, "gmv_max_campaigns", page_size=50):
        if r["campaign_id"] == CID:
            print("black one modify_time (UTC):", r["modify_time"], "| status", r["operation_status"])
    for day in ("2026-10-28",):
        rows = []
        for x in c.iter_gmv_max_report(adv, stores, ["item_id"], M, day, day, page_size=200, filtering={"campaign_ids": [CID], "item_group_ids": [PID]}):
            m = x["metrics"]; rows.append((float(m["cost"]), int(float(m["orders"])), x["dimensions"]["item_id"]))
        if not rows: continue
        rows.sort(reverse=True)
        print("==", day, "items", len(rows), "total", round(sum(r[0] for r in rows)))
        for cost, o, vid in rows:
            tag = OFF.get(vid) and f"  <-- OFF-list ({OFF[vid]})" or (KEEP.get(vid) and f"  (keep: {KEEP[vid]})" or "")
            if cost > 0 or vid in OFF or vid in KEEP:
                print("  ", vid, "cost", round(cost), "orders", o, tag)
