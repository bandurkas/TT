import datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
names = {"1736665360313713735": "Black one", "1737926532373578823": "Black_10", "1736664758417392711": "Premium Putih Mesh", "1737376888451335239": "Abu Abu"}
for a in c.paginate("POST", "/promotion/202309/activities/search", "activities", body={"page_size": 50}, resource="probe"):
    if a["status"] == "ONGOING" and a["activity_type"] == "FLASHSALE":
        f = c.request("GET", "/promotion/202309/activities/" + a["id"], resource="probe")
        print(a["id"], "|", a["title"], "|", a["status"], "|", dt.datetime.fromtimestamp(f["begin_time"], J).strftime("%d.%m %H:%M"), "->", dt.datetime.fromtimestamp(f["end_time"], J).strftime("%d.%m %H:%M"), "|", [names.get(p["id"], p["id"]) for p in f["products"]], "|", [s["activity_price"].get("amount") for p in f["products"] for s in p.get("skus", [])][:2])
