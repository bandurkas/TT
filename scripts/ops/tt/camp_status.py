import json
from src.config.settings import settings
from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_ads.client import TikTokAdsClient
from src.integrations.tiktok_ads import gmv_max
tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load()
c = TikTokAdsClient(tok["access_token"])
for adv in [str(a) for a in tok["advertiser_ids"]]:
    stores = gmv_max.stores(c, adv)
    if not stores: continue
    for ptype in gmv_max.PROMOTION_TYPES:
        for r in c.paginate("/gmv_max/campaign/get/", {"advertiser_id": adv,
                "filtering": {"store_ids": stores, "gmv_max_promotion_types": [ptype]}},
                "gmv_max_campaigns", page_size=50):
            print(ptype[:4], r["campaign_name"][:34].ljust(34), r["campaign_id"], r["operation_status"], r.get("secondary_status"), r["modify_time"])
