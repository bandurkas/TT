import json, re, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
old = json.load(open("/tmp/black10_backup_2026-10-28.json"))
q = c.get_product("1737926532373578823")
oi = [i.get("uri") or i.get("url") for i in old.get("main_images") or []]
ni = [i.get("uri") or i.get("url") for i in q.get("main_images") or []]
print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"), "| updated", dt.datetime.fromtimestamp(q["update_time"], J).strftime("%d.%m %H:%M"))
print("status", q["status"], "| audit", q["audit"]["status"], "| images old", len(oi), "new", len(ni), "| changed", sum(1 for u in ni if u not in oi), "of", len(ni))
print("title:", q["title"][:75])
print("price", q["skus"][0]["price"]["sale_price"], "| stock", q["skus"][0]["inventory"][0]["quantity"], "| weight", q["package_weight"]["value"], "| video", bool(q.get("video")))
a = c.request("GET", "/promotion/202309/activities/7699558284142855937", resource="probe"); print("discount", a["status"], [(x["id"][-6:], x["discount"]) for x in a["products"]])
