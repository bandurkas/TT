import time, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient, ShopApiError
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
AID, PID = "7699561771901224711", "1736665360313713735"
a = c.request("GET", f"/promotion/202309/activities/{AID}", resource="probe")
print("before", a["status"], [(p["id"], p["discount"]) for p in a["products"]])
try:
    c.request("PUT", f"/promotion/202309/activities/{AID}/products", resource="promo_write", body={
        "activity_id": AID, "products": [{"id": PID, "discount": "20", "quantity_limit": -1, "quantity_per_user": -1}]})
except ShopApiError as e:
    print("UPDATE ERR", e.args)
a = c.request("GET", f"/promotion/202309/activities/{AID}", resource="probe")
print("after", a["status"], dt.datetime.fromtimestamp(a["begin_time"], J).strftime("%d.%m %H:%M"), [(p["id"], p["discount"]) for p in a["products"]])
