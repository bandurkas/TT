import json, datetime as dt
from datetime import date
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_ads.client import TikTokAdsClient
from src.integrations.tiktok_ads import gmv_max
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
N = {"1736665360313713735": "black5", "1737926532373578823": "black10", "1737376888451335239": "grey5", "1738054190897136711": "padel", "1737739219254543431": "box jumbo", "1737715582594024519": "putih", "1737660676232610887": "organizer", "1736376427332535367": "unisex5", "1736557623597827143": "kaoskaki5", "1736571964864431175": "anak", "1736664758417392711": "putih mesh", "1737378033298670663": "two tone", "1737378022661719111": "pria putih", "1737324114194564167": "satuan", "1737179641669780551": "subscription", "1736664922058228807": "grey_old"}
d = c.request("GET", "/promotion/202406/coupons/7701473333518386965", resource="probe")["coupon"]
print("COUPON:", d.get("title"), "| source", repr(d.get("creation_source")), "| created", dt.datetime.fromtimestamp(d["create_time"]/1000, J).strftime("%d.%m %H:%M"), "| disc", d["discount"], "| claim", dt.datetime.fromtimestamp(d["claim_duration"]["start_time"], J).strftime("%d.%m %H:%M"), "->", dt.datetime.fromtimestamp(d["claim_duration"]["end_time"], J).strftime("%d.%m"), "| limits", d.get("usage_limits"), "| threshold", d.get("threshold"))
print("  products:", [N.get(p, p[-6:]) for p in d.get("product_ids", [])])
f = c.request("GET", "/promotion/202309/activities/7701482157425477396", resource="probe")
print("BMSM:", f.get("title"), "| created", dt.datetime.fromtimestamp(f["create_time"]/1000, J).strftime("%d.%m %H:%M"), "| level", f.get("product_level"), "| disc", json.dumps(f.get("discount")), "| limit", f.get("participation_limit"))
print("  products:", [N.get(p["id"], p["id"][-6:]) for p in f.get("products", [])])
tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load()
a = TikTokAdsClient(tok["access_token"])
for adv in [str(x) for x in tok["advertiser_ids"]]:
    stores = gmv_max.stores(a, adv)
    if not stores: continue
    for ptype in ("PRODUCT_GMV_MAX", "LIVE_GMV_MAX"):
        for r in a.paginate("/gmv_max/campaign/get/", {"advertiser_id": adv, "filtering": {"store_ids": stores, "gmv_max_promotion_types": [ptype]}}, "gmv_max_campaigns", page_size=50):
            if "affiliate" in r["campaign_name"].lower():
                print("AFF CAMP in list:", ptype, r)
    for x in a.iter_gmv_max_report(adv, stores, ["campaign_id", "stat_time_day"], ["cost", "orders", "gross_revenue"], str(date.today()), str(date.today()), page_size=200):
        pass
    try:
        for x in a.iter_gmv_max_report(adv, stores, ["item_group_id", "stat_time_day"], ["cost", "orders"], "2026-10-28", "2026-10-28", page_size=200, filtering={"campaign_ids": [cid for cid in []]}):
            pass
    except Exception:
        pass
