import json, re, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient, ShopApiError
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
J = dt.timezone(dt.timedelta(hours=7)); print("now", dt.datetime.now(J).strftime("%d.%m %H:%M"))
PID = "1737926532373578823"
p = c.get_product(PID)
json.dump(p, open("/tmp/black10_backup_2026-10-28.json", "w"), ensure_ascii=False)
title, desc = p["title"], p["description"]
def fix(s):
    s2 = re.sub(r"\b10(?=\s*pasang)", "8", s, flags=re.I)
    s2 = re.sub(r"\b20\s*Pcs\b", "16 Pcs", s2, flags=re.I)
    return s2
nt, nd = fix(title), fix(desc)
print("title:", title, "->", nt)
print("desc hits before:", len(re.findall(r"\b10(?=\s*pasang)", desc, re.I)), "+", len(re.findall(r"\b20\s*Pcs", desc, re.I)), "| after:", len(re.findall(r"\b10(?=\s*pasang)", nd, re.I)), "+", len(re.findall(r"\b20\s*Pcs", nd, re.I)), "| '8 pasang' now:", len(re.findall(r"\b8(?=\s*pasang)", nd, re.I)))
print("other '10' left in desc:", re.findall(r".{12}\b10\b.{12}", re.sub(r"<[^>]+>", " ", nd)))
try:
    r = c.request("POST", f"/product/202309/products/{PID}/partial_edit", body={"title": nt, "description": nd}, resource="product_write")
    print("PARTIAL_EDIT OK:", json.dumps(r, ensure_ascii=False)[:300])
except ShopApiError as e:
    print("PARTIAL_EDIT ERR:", str(e.args[0])[:300])
q = c.get_product(PID)
print("readback title:", q["title"])
print("readback status:", q["status"], "| audit", (q.get("audit") or {}).get("status"), "| price", q["skus"][0]["price"]["sale_price"], "| desc 8-hits", len(re.findall(r"\b8(?=\s*pasang)", q["description"], re.I)), "10-hits", len(re.findall(r"\b10(?=\s*pasang)", q["description"], re.I)))
