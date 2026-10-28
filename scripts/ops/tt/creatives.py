import json
from datetime import date
from src.config.settings import settings
from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_ads.client import TikTokAdsClient
from src.integrations.tiktok_ads import gmv_max
tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load()
c = TikTokAdsClient(tok["access_token"])
IDS = {"1876288311852242": "black one", "1878766531029089": "Black_10"}
M = ["cost", "orders", "gross_revenue"]
for adv in [str(a) for a in tok["advertiser_ids"]]:
    stores = gmv_max.stores(c, adv)
    if not stores: continue
    for cid, name in IDS.items():
        groups = {}
        for x in c.iter_gmv_max_report(adv, stores, ["item_group_id", "stat_time_day"], ["cost"], "2026-10-11", str(date.today()), page_size=200, filtering={"campaign_ids": [cid]}):
            groups[x["dimensions"]["item_group_id"]] = 1
        for g in groups:
            rows = []
            try:
                for x in c.iter_gmv_max_report(adv, stores, ["item_id"], M, "2026-10-11", str(date.today()), page_size=200, filtering={"campaign_ids": [cid], "item_group_ids": [g]}):
                    m = x["metrics"]; rows.append((float(m["cost"]), int(float(m["orders"])), float(m["gross_revenue"]), x["dimensions"]["item_id"]))
            except Exception as e:
                print(name, g, "ERR", str(e)[:100]); continue
            rows.sort(reverse=True)
            print("==", name, "product", g, "creatives", len(rows), "total cost", round(sum(r[0] for r in rows)), "orders", sum(r[1] for r in rows))
            for cost, o, gr, vid in rows[:12]:
                print("  ", vid, "cost", round(cost), "orders", o, "gmv", round(gr), "cpo", round(cost / o) if o else "-")
