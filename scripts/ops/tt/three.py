import json, datetime as dt
from datetime import date
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient, ShopApiError
from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_ads.client import TikTokAdsClient
from src.integrations.tiktok_ads import gmv_max
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7)); print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"))
# 1. affiliate_PC
tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load(); a = TikTokAdsClient(tok["access_token"])
adv = "7658353454934671368"; stores = gmv_max.stores(a, adv)
found = [r for ptype in ("PRODUCT_GMV_MAX", "LIVE_GMV_MAX") for r in a.paginate("/gmv_max/campaign/get/", {"advertiser_id": adv, "filtering": {"store_ids": stores, "gmv_max_promotion_types": [ptype]}}, "gmv_max_campaigns", page_size=50) if r["campaign_id"] == "1880233555330114"]
print("affiliate_PC in campaign list:", found or "NOT LISTED")
for x in a.iter_gmv_max_report(adv, stores, ["campaign_id", "stat_time_day"], ["cost", "orders"], str(date.today()), str(date.today()), page_size=200):
    if x["dimensions"]["campaign_id"] == "1880233555330114":
        print("affiliate_PC spend today (report):", x["metrics"])
# 2/3. discounts
for aid, pid, disc, n, base in (("7699561771901224711", "1736665360313713735", "26", "black5", 85000), ("7699558284142855937", "1737926532373578823", "25", "black10", 132000)):
    try:
        c.request("PUT", f"/promotion/202309/activities/{aid}/products", resource="promo_write", body={
            "activity_id": aid, "products": [{"id": pid, "discount": disc, "quantity_limit": -1, "quantity_per_user": -1}]})
    except ShopApiError as e:
        print(n, "ERR", str(e.args[0])[:200])
    f = c.request("GET", f"/promotion/202309/activities/{aid}", resource="probe")
    p = c.get_product(pid); b = int(p["skus"][0]["price"]["sale_price"]); d = int(f["products"][0]["discount"]) if f["products"] else None
    print(n, f["status"], "base", b, "disc", d, "-> buyer", round(b * (100 - d) / 100) if d else None)
d = c.request("GET", "/promotion/202406/coupons/7701473333518386965", resource="probe")["coupon"]; print("coupon 4%:", d["status"])
