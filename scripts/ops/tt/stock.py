import json, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient, ShopApiError
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"))
SOLD = ["1737926532373578823", "1737660676232610887", "1737376888451335239", "1736665360313713735", "1736664758417392711"]
for pid in SOLD:
    p = c.get_product(pid)
    zero = [s for s in p["skus"] if sum(int(i["quantity"]) for i in s["inventory"]) <= 0]
    print(pid[-6:], p["status"], p["title"][:30], "| stock", [sum(int(i["quantity"]) for i in s["inventory"]) for s in p["skus"]], "| zero:", len(zero))
    if not zero or p["status"] != "ACTIVATE":
        continue
    body = {"skus": [{"id": s["id"], "inventory": [{"warehouse_id": s["inventory"][0]["warehouse_id"], "quantity": 300}]} for s in zero]}
    try:
        r = c.request("POST", f"/product/202309/products/{pid}/inventory/update", body=body, resource="product_write")
        print("  UPDATED", json.dumps(r)[:120])
    except ShopApiError as e:
        print("  UPDATE ERR", e.args); continue
    q = c.get_product(pid)
    print("  after:", [(s["id"][-5:], sum(int(i["quantity"]) for i in s["inventory"])) for s in q["skus"]])
