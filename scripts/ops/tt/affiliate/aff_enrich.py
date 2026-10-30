import json, time, sys
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"), settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t, shop_cipher=settings.tiktok_shop_shop_cipher or None)
A = "/affiliate_seller/"
def go(m, p, q=None, b=None):
    for i in range(4):
        try:
            r = c.request(m, A + p, query=q, body=b, resource="probe"); time.sleep(1.0); return r
        except Exception as e:
            s = str(e)
            if "36009002" in s or "429" in s: time.sleep(8 * (i + 1)); continue
            return {"_err": s[:200]}
    return {"_err": "rate"}
ids = json.load(open("/tmp/shortlist_ids.json"))
out = {}
for i, oid in enumerate(ids):
    r = go("GET", "202608/marketplace_creators/" + oid, q={"data_groups": "BASIC_CREATOR_INFORMATION,CONTENT_PERFORMANCE,SALES_AND_GMV,COLLABORATION"})
    if "_err" in r:
        out[oid] = r; continue
    cr = r.get("creator", r); cr.pop("avatar", None)
    out[oid] = cr
    if i == 0:
        print("SAMPLE", json.dumps(cr, ensure_ascii=False)[:2500])
json.dump(out, open("/tmp/enriched.json", "w"), ensure_ascii=False)
print("enriched", len(out), "errors", sum(1 for v in out.values() if "_err" in v))
# eligibility in batches of 100
elig = {}
for i in range(0, len(ids), 100):
    r = go("POST", "202610/creator_outreach/eligibility/check", b={"creator_infos": [{"creator_open_id": x} for x in ids[i:i + 100]]})
    if "_err" in r:
        print("ELIG ERR", r); continue
    for e in r.get("creator_eligibility_results", []):
        elig[e["creator_open_id"]] = e
    print("batch quota consumable:", r.get("is_batch_quota_consumable"))
json.dump(elig, open("/tmp/elig.json", "w"), ensure_ascii=False)
print("elig", len(elig), "blocked", sum(1 for e in elig.values() if e.get("is_blocked")), "connected", sum(1 for e in elig.values() if e.get("is_connected")), "no quota", sum(1 for e in elig.values() if not e.get("is_creator_level_quota_available")), "follower threshold fail", sum(1 for e in elig.values() if not e.get("is_creator_follower_count_threshold_met")))
