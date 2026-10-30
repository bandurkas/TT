"""Create target collaborations. Usage inside worker: python -I - < aff_create.py  (reads /tmp/batches.json, /tmp/invite_text_id.txt)
/tmp/batches.json: {"dry_run": true/false, "batches": [{"name": "...", "open_ids": [...]}, ...]}
"""
import json, time, datetime as dt
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"), settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t, shop_cipher=settings.tiktok_shop_shop_cipher or None)
A = "/affiliate_seller/"
cfg = json.load(open("/tmp/batches.json"))
MSG = open("/tmp/invite_text_v2.txt", encoding="utf-8").read().strip()
SET8, BLACK5 = "1737926532373578823", "1736665360313713735"
PRODUCTS = [{"id": SET8, "target_commission_rate": 2500}, {"id": BLACK5, "target_commission_rate": 2000}]
END = str(int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=90)).timestamp()))
CONTACT = {"whatsapp": "(+62) 85888014696"}
SAMPLE = {"has_free_sample": False, "is_sample_approval_exempt": False}
def go(m, p, q=None, b=None):
    for i in range(3):
        try:
            r = c.request(m, A + p, query=q, body=b, resource="probe"); time.sleep(1.5); return r
        except Exception as e:
            s = str(e)
            if "36009002" in s or "429" in s: time.sleep(10 * (i + 1)); continue
            print("ERR", p, s[:400]); time.sleep(1.5); return None
    return None
results = []
for b in cfg["batches"]:
    ids = b["open_ids"]
    assert len(ids) <= 50
    conf = go("POST", "202605/target_collaborations/conflicts/check", b={"creator_open_id_list": ids, "product_id_list": [SET8, BLACK5]})
    print("CONFLICTS", b["name"], json.dumps(conf, ensure_ascii=False)[:600] if conf else "ERR")
    if conf and conf.get("has_conflict"):
        bad = {x["creator_open_id"] for x in conf.get("conflict_items", [])}
        print("  dropping", len(bad), "conflicting creators")
        ids = [x for x in ids if x not in bad]
    body = {"name": b["name"], "message": MSG, "end_time": END, "products": PRODUCTS, "creator_user_open_ids": ids,
            "seller_contact_info": CONTACT, "free_sample_rule": SAMPLE, "preferred_content_type": "VIDEO"}
    if cfg.get("dry_run"):
        print("DRY RUN body:", json.dumps({**body, "message": MSG[:60] + "..."}, ensure_ascii=False)[:1500]); continue
    r = go("POST", "202508/target_collaborations", b=body)
    print("CREATE", b["name"], json.dumps(r, ensure_ascii=False)[:1500] if r else "ERR")
    if not r: continue
    cid = (r.get("target_collaboration") or {}).get("id")
    results.append({"name": b["name"], "id": cid, "sent": len(ids), "invalid_open_ids": r.get("invalid_open_id_list"), "invalid_products": r.get("invalid_product_id_list"), "conflicts": r.get("target_collaboration_conflicts")})
    if cid:
        d = go("GET", "202508/target_collaborations/" + cid)
        if d:
            tc = d["target_collaboration"]
            print("READBACK", cid, "invited", tc.get("creator_invited_count"), "products", [(p["id"][-6:], p["commission"].get("rate"), p["commission"].get("shop_ads_commission_rate")) for p in tc.get("products", [])], "end", tc.get("end_time"), "sample", tc.get("free_sample_rule"), "contact", tc.get("seller_contact_info"), "msg_len", len(tc.get("message") or ""))
json.dump(results, open("/tmp/create_results.json", "w"), ensure_ascii=False)
print("DONE", json.dumps(results, ensure_ascii=False)[:2000])
