import time
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient, ShopApiError
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
PID = "1736665360313713735"
now = int(time.time())
a = c.request("POST", "/promotion/202309/activities", resource="promo_write", body={
    "title": "Discount Black 29% v1", "activity_type": "DIRECT_DISCOUNT", "begin_time": now + 600,
    "end_time": now + 180 * 86400, "product_level": "PRODUCT"})
aid = a["activity_id"]
try:
    c.request("PUT", f"/promotion/202309/activities/{aid}/products", resource="promo_write", body={
        "activity_id": aid, "products": [{"id": PID, "discount": "29", "quantity_limit": -1, "quantity_per_user": -1}]})
    f = c.request("GET", f"/promotion/202309/activities/{aid}", resource="probe")
    print("BLACK OK", aid, f["status"], f["begin_time"], [(p["id"], p["discount"]) for p in f["products"]])
except ShopApiError as e:
    print("BLACK BLOCKED", e.args)
    print("cleanup", c.request("POST", f"/promotion/202309/activities/{aid}/deactivate", body={"activity_id": aid}, resource="promo_write").get("status"))
