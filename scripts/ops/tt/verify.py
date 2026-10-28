import time, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
B = {"1736665360313713735": "black5", "1737926532373578823": "black10"}
print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"), "Jakarta")
for pid, n in B.items():
    p = c.get_product(pid)
    print(n, p["status"], [(s["price"]["sale_price"], s["inventory"][0]["quantity"]) for s in p["skus"]], "w", p["package_weight"]["value"])
print("ACTIVITIES (ONGOING/NOT_START):")
for a in c.paginate("POST", "/promotion/202309/activities/search", "activities", body={"page_size": 50}, resource="probe"):
    if a["status"] in ("ONGOING", "NOT_START"):
        f = c.request("GET", "/promotion/202309/activities/" + a["id"], resource="probe")
        pr = [(B.get(p["id"], p["id"][-6:]), p.get("discount")) for p in f.get("products", [])]
        print(" ", a["id"], a["activity_type"], a["status"], a["title"][:34], "begin", dt.datetime.fromtimestamp(f["begin_time"], J).strftime("%d.%m %H:%M"), pr, f.get("discount"))
print("COUPONS touching black:")
n = 0
for r in c.paginate("POST", "/promotion/202406/coupons/search", "coupons", body={"page_size": 50}, resource="probe"):
    if r["status"] == "ONGOING":
        d = c.request("GET", "/promotion/202406/coupons/" + r["id"], resource="probe")["coupon"]
        if d.get("product_scope") == "FULL_SHOP" or set(d.get("product_ids") or []) & set(B):
            print(" ", r["id"], d["discount"], d.get("product_scope"), d.get("product_ids")); n += 1
print("  count", n)
