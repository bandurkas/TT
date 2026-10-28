import datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient, ShopApiError
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"))
for aid, pid, disc, n in (("7699561771901224711", "1736665360313713735", "20", "black5"), ("7699558284142855937", "1737926532373578823", "17", "black10")):
    try:
        c.request("PUT", f"/promotion/202309/activities/{aid}/products", resource="promo_write", body={
            "activity_id": aid, "products": [{"id": pid, "discount": disc, "quantity_limit": -1, "quantity_per_user": -1}]})
        f = c.request("GET", f"/promotion/202309/activities/{aid}", resource="probe")
        print(n, "RESTORED", f["status"], [(p["id"][-6:], p["discount"]) for p in f["products"]])
    except ShopApiError as e:
        print(n, "BLOCKED", str(e.args[0])[:230])
print("flash deals (last 48h):")
for a in c.paginate("POST", "/promotion/202309/activities/search", "activities", body={"page_size": 50}, resource="probe"):
    if a["activity_type"] == "FLASHSALE" and a["create_time"]/1000 > 1792600000:
        f = c.request("GET", "/promotion/202309/activities/" + a["id"], resource="probe")
        print(" ", a["id"][-6:], a["status"], "created", dt.datetime.fromtimestamp(a["create_time"]/1000, J).strftime("%d.%m %H:%M"), "updated", dt.datetime.fromtimestamp(a["update_time"]/1000, J).strftime("%d.%m %H:%M"), [p["id"][-6:] for p in f.get("products", [])])
