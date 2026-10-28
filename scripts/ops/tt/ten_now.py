import datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"))
for aid in ("7699558284142855937", "7699561771901224711"):
    a = c.request("GET", f"/promotion/202309/activities/{aid}", resource="probe")
    print(aid, a["status"], [(p["id"][-6:], p["discount"]) for p in a["products"]])
