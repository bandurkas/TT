import datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient, ShopApiError
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
PID, AID = "1737926532373578823", "7699558284142855937"
print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"))
p = c.get_product(PID); sku = p["skus"][0]["id"]
a = c.request("GET", f"/promotion/202309/activities/{AID}", resource="probe")
print("before: base", p["skus"][0]["price"]["sale_price"], "| act", a["status"], [x["discount"] for x in a["products"]])
try:
    c.request("PUT", f"/promotion/202309/activities/{AID}/products", resource="promo_write", body={
        "activity_id": AID, "products": [{"id": PID, "discount": "17", "quantity_limit": -1, "quantity_per_user": -1}]})
    c.request("POST", f"/product/202309/products/{PID}/prices/update", resource="product_write",
              body={"skus": [{"id": sku, "price": {"amount": "132000", "currency": "IDR"}}]})
except ShopApiError as e:
    print("ERR", e.args)
p = c.get_product(PID); a = c.request("GET", f"/promotion/202309/activities/{AID}", resource="probe")
base = int(p["skus"][0]["price"]["sale_price"]); d = int(a["products"][0]["discount"])
print("after: base", base, "| act", a["status"], d, "% -> buyer", round(base * (100 - d) / 100), "| stock", p["skus"][0]["inventory"][0]["quantity"])
