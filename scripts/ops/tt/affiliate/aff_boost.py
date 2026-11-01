"""Target collaboration 15 % for creators who already sold via open collaboration. Default = dry (resolve + checks). --create = send."""
import json, os, sys, time, datetime as dt, collections
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
CREATE = "--create" in sys.argv
ONLY_BIG = "--only-big" in sys.argv          # second wave: only level >= 7
NEED_RESET = "--need-reset" in sys.argv      # exit 3 until weekly quota for level 7-8 has reset
BIG = int(sys.argv[sys.argv.index("--big") + 1]) if "--big" in sys.argv else None   # cap on level >= 7 creators
TAG = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "Seller"
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"), settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t, shop_cipher=settings.tiktok_shop_shop_cipher or None)
A = "/affiliate_seller/"
J = dt.timezone(dt.timedelta(hours=7))
NOW = dt.datetime.now(J)
SINCE = int(dt.datetime(2026, 10, 1, 0, 0, tzinfo=J).timestamp())
SET8, BLACK5 = "1737926532373578823", "1736665360313713735"
RATE = 1500
PRODUCTS = [{"id": SET8, "target_commission_rate": RATE}, {"id": BLACK5, "target_commission_rate": RATE}]
CONTACT = {"whatsapp": "(+62) 85888014696"}
SAMPLE = {"has_free_sample": False, "is_sample_approval_exempt": False}
NAME = f"Lomira Komisi 15 Nov26 {TAG}"[:30]
MSG = ("Halo Kak! Terima kasih sudah menjualkan kaos kaki LOMIRA lewat link Kakak.\n\n"
       "Sebagai apresiasi, kami naikkan komisi khusus untuk Kakak menjadi 15%:\n"
       "Kaos Kaki Hitam 5 Pasang (Rp62.900): komisi 15%, sekitar Rp9.400 per paket.\n"
       "Paket 8 Pasang Kaos Kaki Hitam (Rp99.000): komisi 15%, sekitar Rp14.800 per paket.\n\n"
       "Terima undangan ini supaya komisi 15% langsung aktif di showcase Kakak. Stok ready, kirim cepat.\n"
       "Ada pertanyaan? Chat kami ya.")
LEDGER = "/app/data/affiliate/ledger.json"
def go(m, p, q=None, b=None):
    for i in range(5):
        try:
            r = c.request(m, A + p, query=q, body=b, resource="probe"); time.sleep(1.2); return r
        except Exception as e:
            s = str(e)
            if "36009002" in s or "429" in s: time.sleep(8 * (i + 1)); continue
            print("ERR", p, s[:300]); return None
    print("ERR ratelimit", p); return None
print("now", NOW.strftime("%d.%m %H:%M"), "mode", "CREATE" if CREATE else "DRY")

# 1. sellers from affiliate orders since 01.10
tok = None; orders = []
for _ in range(30):
    q = {"page_size": 20}
    if tok: q["page_token"] = tok
    r = go("POST", "202410/orders/search", q=q, b={"create_time_ge": SINCE})
    if not r: break
    orders += r.get("orders") or []
    tok = r.get("next_page_token")
    if not tok: break
sellers = collections.defaultdict(lambda: {"orders": 0, "qty": 0, "base": 0, "comm": 0, "target": 0, "last": 0})
for o in orders:
    for s in o["skus"]:
        u = s.get("creator_username")
        if not u: continue
        d = sellers[u]; d["orders"] += 1; d["qty"] += s.get("quantity") or 0
        d["base"] += int(float((s.get("estimated_commission_base") or {}).get("amount") or 0))
        d["comm"] += int(float((s.get("estimated_paid_commission") or {}).get("amount") or 0))
        if s.get("target_collaboration_id"): d["target"] += 1
        d["last"] = max(d["last"], o["create_time"])
print("affiliate orders since 01.10:", len(orders), "sellers:", len(sellers))

# 2. resolve username -> open_id
resolved = {}
for u, d in sorted(sellers.items(), key=lambda kv: -kv[1]["orders"]):
    r = go("POST", "202608/marketplace_creators/search", q={"page_size": 12}, b={"keyword": u})
    hit = next((x for x in (r or {}).get("creators", []) if (x.get("username") or "").lower() == u.lower()), None)
    if hit:
        resolved[u] = {"open_id": hit["creator_open_id"], "level": (hit.get("creator_profile") or {}).get("creator_level"), "followers": hit.get("follower_count"),
                       "gmv": (hit.get("gmv") or {}).get("amount"), **d}
    else:
        print("  not found in marketplace:", u, d["orders"], "orders")
print("resolved", len(resolved), "of", len(sellers))

# 3. exclude already in ONGOING target collabs
excl = set()
r = go("POST", "202508/target_collaborations/search", q={"page_size": 20}, b={"collaboration_status": "ONGOING"})
for x in (r or {}).get("target_collaborations", []):
    d = go("GET", "202508/target_collaborations/" + x["id"])
    for cr in (d or {}).get("target_collaboration", {}).get("creators", []): excl.add(cr["creator_open_id"])
cand = {u: v for u, v in resolved.items() if v["open_id"] not in excl}
print("already in target collabs:", len(resolved) - len(cand))

# 4. eligibility + conflicts
ids = [v["open_id"] for v in cand.values()]
elig = {}
for i in range(0, len(ids), 100):
    r = go("POST", "202610/creator_outreach/eligibility/check", b={"creator_infos": [{"creator_open_id": z} for z in ids[i:i + 100]]})
    for e in (r or {}).get("creator_eligibility_results", []): elig[e["creator_open_id"]] = e
bad = {}
for i in range(0, len(ids), 50):
    r = go("POST", "202605/target_collaborations/conflicts/check", b={"creator_open_id_list": ids[i:i + 50], "product_id_list": [SET8, BLACK5]})
    for z in (r or {}).get("conflict_items", []): bad[z["creator_open_id"]] = json.dumps({k: v for k, v in z.items() if k != "creator_open_id"}, ensure_ascii=False)[:160]
ok = []
print(f"{'username':20} {'lvl':>3} {'fol':>8} {'ord':>3} {'qty':>3} {'base_k':>6} {'comm_k':>6} status")
for u, v in sorted(cand.items(), key=lambda kv: -kv[1]["orders"]):
    g = elig.get(v["open_id"]) or {}
    lvl = g.get("creator_level", v["level"])
    st = []
    if not g: st.append("no_elig")
    if g.get("is_blocked"): st.append("blocked")
    if g.get("is_connected") or g.get("is_paired"): st.append("connected")
    if g and not g.get("is_creator_follower_count_threshold_met"): st.append("followers<min")
    if g and not g.get("is_creator_level_quota_available"): st.append("no_quota")
    if v["open_id"] in bad: st.append("CONFLICT " + bad[v["open_id"]])
    print(f"{u:20} {str(lvl):>3} {str(v['followers']):>8} {v['orders']:>3} {v['qty']:>3} {v['base']//1000:>6} {v['comm']//1000:>6} {' '.join(st) or 'OK'}")
    if not st: ok.append({**v, "username": u, "level": lvl})
q = go("GET", "202607/creator_outreach/quota")
big_use = None
if q:
    print("quota", q["data"].get("quota_use"), [(d["creator_levels"], d["quota_period_use"], d["quota_period_sum"]) for d in q["data"]["quota_details"]])
    big_use = next((d["quota_period_use"] for d in q["data"]["quota_details"] if 7 in d["creator_levels"]), None)
if NEED_RESET and (big_use is None or big_use > 20):
    print("quota 7-8 not reset yet (use", big_use, ") -> exit 3"); sys.exit(3)
USERS = set(sys.argv[sys.argv.index("--users") + 1].split(",")) if "--users" in sys.argv else None
if USERS: ok = [x for x in ok if x["username"] in USERS]
if ONLY_BIG: ok = [x for x in ok if (x["level"] or 0) >= 7]
if BIG is not None:
    big = [x for x in ok if (x["level"] or 0) >= 7][:BIG]
    ok = [x for x in ok if (x["level"] or 0) < 7] + big
print("to send:", len(ok), "levels", dict(collections.Counter(x["level"] for x in ok)), [x["username"] for x in ok])
json.dump(ok, open("/tmp/boost_ok.json", "w"), ensure_ascii=False)
if not CREATE or not ok:
    print("DRY done" if not CREATE else "nothing to send"); sys.exit(0)

# 5. create
END = str(int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=90)).timestamp()))
ledger = json.load(open(LEDGER)) if os.path.exists(LEDGER) else {"sent": {}, "last_sent": None, "runs": []}
created = []
for i, part in enumerate([ok[j:j + 50] for j in range(0, len(ok), 50)]):
    name = (NAME + (f" {chr(65 + i)}" if len(ok) > 50 else ""))[:30]
    body = {"name": name, "message": MSG, "end_time": END, "products": PRODUCTS, "creator_user_open_ids": [x["open_id"] for x in part],
            "seller_contact_info": CONTACT, "free_sample_rule": SAMPLE, "preferred_content_type": "VIDEO"}
    r = go("POST", "202508/target_collaborations", b=body)
    cid = ((r or {}).get("target_collaboration") or {}).get("id")
    print("CREATE", name, "->", cid, "invalid", (r or {}).get("invalid_open_id_list"), "conflicts", (r or {}).get("target_collaboration_conflicts"))
    if not cid: continue
    d = go("GET", "202508/target_collaborations/" + cid)
    tc = (d or {}).get("target_collaboration", {})
    print("READBACK", cid, "invited", tc.get("creator_invited_count"), "rates", [(p["id"][-6:], p["commission"].get("rate")) for p in tc.get("products", [])],
          "end", tc.get("end_time"), "sample", tc.get("free_sample_rule"), "contact", tc.get("seller_contact_info"), "msg_len", len(tc.get("message") or ""))
    created.append({"name": name, "id": cid, "n": len(part)})
    for x in part:
        ledger["sent"][x["open_id"]] = {"username": x["username"], "date": NOW.isoformat(), "collab": cid, "level": x["level"], "score": None, "note": "seller boost 15%"}
if created:
    ledger["runs"].append({"date": NOW.isoformat(), "created": created, "sent": sum(z["n"] for z in created), "note": "seller boost 15%, manual; last_sent untouched"})
    json.dump(ledger, open(LEDGER, "w"), ensure_ascii=False, indent=1)
print("DONE", created)
if not created: sys.exit(4)
