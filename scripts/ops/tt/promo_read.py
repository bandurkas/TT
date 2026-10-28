from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
print("ACT")
for a in c.paginate("POST", "/promotion/202309/activities/search", "activities", body={"page_size": 50}, resource="probe"):
    if a["status"] in ("ONGOING", "NOT_START"):
        f = c.request("GET", "/promotion/202309/activities/" + a["id"], resource="probe")
        print(" ", a["id"], a["activity_type"], a["status"], a["title"][:36], [(p["id"], p.get("discount")) for p in f.get("products", [])])
print("COUPON")
for r in c.paginate("POST", "/promotion/202406/coupons/search", "coupons", body={"page_size": 50}, resource="probe"):
    if r["status"] == "ONGOING":
        d = c.request("GET", "/promotion/202406/coupons/" + r["id"], resource="probe")["coupon"]
        print(" ", r["id"], d["discount"].get("percentage") or d["discount"].get("reduction_amount",{}).get("amount"), d.get("product_scope"), d.get("product_ids"), r["title"][:28])
for pid in ("1737376888451335239","1736665360313713735","1737926532373578823"):
    p = c.get_product(pid); print(pid, [s["price"]["sale_price"] for s in p["skus"]])
