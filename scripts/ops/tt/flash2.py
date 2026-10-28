import json, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
for aid, n in (("7700832767483053830", "black5"), ("7700825797931173652", "black10")):
    f = c.request("GET", "/promotion/202309/activities/" + aid, resource="probe")
    print(n, aid, f["status"], dt.datetime.fromtimestamp(f["begin_time"], J).strftime("%d.%m %H:%M"), "->", dt.datetime.fromtimestamp(f["end_time"], J).strftime("%d.%m %H:%M"))
    for p in f["products"]:
        print("   skus", [(s["id"][-5:], s["activity_price"].get("amount"), s.get("quantity_limit"), s.get("quantity_per_user")) for s in p.get("skus", [])])
