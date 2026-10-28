import re, time, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7))
for i in range(10):
    q = c.get_product("1737926532373578823")
    au = (q.get("audit") or {}).get("status")
    eight = len(re.findall(r"\b8(?=\s*pasang)", q["title"] + q["description"], re.I))
    print(dt.datetime.now(J).strftime("%H:%M:%S"), "status", q["status"], "| audit", au, "| has_draft", q.get("has_draft"), "| title has 8:", "8 Pasang" in q["title"], "| 8-hits", eight)
    if au != "AUDITING" and eight > 0:
        break
    time.sleep(30)
