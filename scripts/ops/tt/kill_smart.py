import json, datetime as dt
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
try:
    r = c.request("POST", "/promotion/202406/coupons/7701473333518386965/deactivate", body={"coupon_id": "7701473333518386965"}, resource="promo_write")
    print("coupon 4%:", json.dumps(r)[:150])
except ShopApiError as e:
    print("coupon 4% ERR:", str(e.args[0])[:160])
try:
    r = c.request("POST", "/promotion/202309/activities/7701482157425477396/deactivate", body={"activity_id": "7701482157425477396"}, resource="promo_write")
    print("BMSM 1%:", r.get("status"))
except ShopApiError as e:
    print("BMSM 1% ERR:", str(e.args[0])[:160])
d = c.request("GET", "/promotion/202406/coupons/7701473333518386965", resource="probe")["coupon"]; print("coupon readback:", d["status"])
f = c.request("GET", "/promotion/202309/activities/7701482157425477396", resource="probe"); print("bmsm readback:", f["status"])
tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load(); a = TikTokAdsClient(tok["access_token"])
N = {"1736665360313713735": "black5", "1737926532373578823": "black10", "1737376888451335239": "grey5"}
for adv in ("7658353454934671368",):
    stores = gmv_max.stores(a, adv)
    for x in a.iter_gmv_max_report(adv, stores, ["item_group_id", "stat_time_day"], ["cost", "orders"], "2026-10-28", "2026-10-28", page_size=200, filtering={"campaign_ids": ["1880233555330114"]}):
        print("affiliate_PC product:", N.get(x["dimensions"]["item_group_id"], x["dimensions"]["item_group_id"]), x["metrics"])
