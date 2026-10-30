import json, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"),
                      settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t,
                     shop_cipher=settings.tiktok_shop_shop_cipher or None)
A = "/affiliate_seller/"
J = dt.timezone(dt.timedelta(hours=7))
N = {"1736665360313713735": "black5", "1737926532373578823": "set8", "1737376888451335239": "grey5", "1738054190897136711": "padel", "1737715582594024519": "putih", "1737660676232610887": "organizer"}
def tm(x):
    return dt.datetime.fromtimestamp(int(x), J).strftime("%d.%m %H:%M") if x else "-"

print("== OPEN COLLABORATIONS")
for o in c.paginate("POST", A + "202409/open_collaborations/search", "open_collaborations", body={}, resource="probe", page_size=20):
    p = o["product"]
    print(" ", N.get(p["id"], p["id"][-6:]), p["status"], "rate", o["current_commission"]["rate"], "creators", o["content_creator_count"], "showcase", o["showcase_creator_count"], "approve", o["require_seller_approve_creator"], o["status"], "price", p["original_price"]["minimum_amount"])

print("== SAMPLE APPLICATIONS")
n = 0
for s in c.paginate("POST", A + "202409/sample_applications/search", "sample_applications", body={}, resource="probe", page_size=20):
    n += 1
    cr = s["creator"]
    d = {k: v for k, v in s.items() if k not in ("creator", "product")}
    print(" ", N.get(s["product"]["id"], s["product"]["id"][-6:]), "|", cr.get("username"), "fol", cr.get("follower_count"), "gmv", cr.get("gmv", {}).get("amount"), "views", cr.get("ec_video_view"), "|", json.dumps(d, ensure_ascii=False)[:420])
print("  total", n)

print("== TARGET COLLABS")
for st in ("ONGOING", "NOT_STARTED", "ENDED", "UNPUBLISHED", "ALL"):
    try:
        r = c.request("POST", A + "202409/target_collaborations/search", query={"page_size": 20}, body={"collaboration_status": st}, resource="probe")
        print(" ", st, "OK", json.dumps(r, ensure_ascii=False)[:500])
    except Exception as e:
        print(" ", st, "ERR", str(e)[:160])

print("== MARKETPLACE CREATORS")
try:
    r = c.request("POST", A + "202406/marketplace_creators/search", query={"page_size": 12}, body={}, resource="probe")
    cs = r.get("creators") or []
    print("  keys", list(r.keys()), "n", len(cs), "total", r.get("total_count"))
    for x in cs[:3]:
        print("  ", json.dumps(x, ensure_ascii=False)[:500])
except Exception as e:
    print("  ERR", str(e)[:300])

print("== CONVERSATIONS")
for cv in ("7700826899387875592", "7682661981890953479", "7666534800178250002"):
    try:
        r = c.request("GET", A + f"202412/conversation/{cv}/messages", query={"page_size": 5}, resource="probe")
        print(" ", cv, json.dumps(r, ensure_ascii=False)[:600])
    except Exception as e:
        print(" ", cv, "ERR", str(e)[:160])
