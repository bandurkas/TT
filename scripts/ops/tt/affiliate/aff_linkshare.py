"""Link-share hunters: marketplace creators with few followers but real sales (no video) -> target plan 15 %.
Default = dry. --create sends levels 0-6 now (cap SMALL_CAP) and saves levels 7-8 to /app/data/affiliate/linkshare_big.json.
--big-only [--cap N] [--need-reset]: send saved level 7-8 list (after weekly quota reset)."""
import json, os, sys, time, datetime as dt, collections
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
CREATE = "--create" in sys.argv
BIG_ONLY = "--big-only" in sys.argv
NEED_RESET = "--need-reset" in sys.argv
CAP = int(sys.argv[sys.argv.index("--cap") + 1]) if "--cap" in sys.argv else 40
SMALL_CAP = 100
ENRICH_N = 160
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"), settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t, shop_cipher=settings.tiktok_shop_shop_cipher or None)
A = "/affiliate_seller/"
J = dt.timezone(dt.timedelta(hours=7)); NOW = dt.datetime.now(J)
SET8, BLACK5 = "1737926532373578823", "1736665360313713735"
PRODUCTS = [{"id": SET8, "target_commission_rate": 1500}, {"id": BLACK5, "target_commission_rate": 1500}]
CONTACT = {"whatsapp": "(+62) 85888014696"}
SAMPLE = {"has_free_sample": False, "is_sample_approval_exempt": False}
DATA = "/app/data/affiliate"; LEDGER = f"{DATA}/ledger.json"; BIGF = f"{DATA}/linkshare_big.json"
MSG = ("Halo! Kami LOMIRA, brand kaos kaki katun premium (85% katun, adem, anti bau), sudah terjual ribuan pasang di TikTok Shop dan laku lewat link share.\n\n"
       "Komisi 15% untuk Kakak:\n"
       "Kaos Kaki Hitam 5 Pasang (Rp62.900): komisi sekitar Rp9.400 per paket.\n"
       "Paket 8 Pasang Kaos Kaki Hitam (Rp99.000): komisi sekitar Rp14.800 per paket.\n\n"
       "Harga terjangkau, cepat laku, stok ready, kirim cepat. Cocok dibagikan di grup, kanal, website, atau konten apa pun.\n"
       "Terima undangan ini dan bagikan link produknya hari ini! Ada pertanyaan? Chat kami ya.")
def go(m, p, q=None, b=None):
    for i in range(5):
        try:
            r = c.request(m, A + p, query=q, body=b, resource="probe"); time.sleep(1.1); return r
        except Exception as e:
            s = str(e)
            if "36009002" in s or "429" in s: time.sleep(8 * (i + 1)); continue
            raise
    raise RuntimeError("rate limit " + p)
def num(v):
    try: return float(v["amount"]) if isinstance(v, dict) else float(v)
    except (TypeError, ValueError, KeyError): return None
print("now", NOW.strftime("%d.%m %H:%M"), "mode", "BIG_ONLY" if BIG_ONLY else ("CREATE" if CREATE else "DRY"))
ledger = json.load(open(LEDGER)) if os.path.exists(LEDGER) else {"sent": {}, "last_sent": None, "runs": []}

q = go("GET", "202607/creator_outreach/quota")
qd = q["data"]; cap = {}
for d in qd["quota_details"]:
    rem = -1 if d["quota_period_sum"] == -1 else max(0, d["quota_period_sum"] - d["quota_period_use"] - 2)
    for lv in d["creator_levels"]: cap[lv] = rem
big_use = next((d["quota_period_use"] for d in qd["quota_details"] if 7 in d["creator_levels"]), None)
print("quota use", qd.get("quota_use"), "remaining:", {k: v for k, v in cap.items() if k in (2, 4, 6, 8)}, "7-8 use", big_use)
if NEED_RESET and (big_use is None or big_use > 20):
    print("quota 7-8 not reset yet -> exit 3"); sys.exit(3)

excl = set(ledger["sent"])
r = go("POST", "202508/target_collaborations/search", q={"page_size": 20}, b={"collaboration_status": "ONGOING"})
for x in (r or {}).get("target_collaborations", []):
    d = go("GET", "202508/target_collaborations/" + x["id"])
    for cr in (d or {}).get("target_collaboration", {}).get("creators", []): excl.add(cr["creator_open_id"])
print("excluded:", len(excl))

test_accounts = []; created = []
def create(part, tag):
    name = f"Lomira K15 Nov26 {tag}"[:30]
    body = {"name": name, "message": MSG, "end_time": str(int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=90)).timestamp())), "products": PRODUCTS,
            "creator_user_open_ids": [x["open_id"] for x in part], "seller_contact_info": CONTACT, "free_sample_rule": SAMPLE, "preferred_content_type": "VIDEO"}
    try:
        r = go("POST", "202508/target_collaborations", b=body)
    except Exception as e:
        s = str(e)
        if "16024004" in s:
            if len(part) == 1:
                test_accounts.append(part[0]["username"]); print("  test account:", part[0]["username"]); return
            m = len(part) // 2; create(part[:m], tag + "1"); create(part[m:], tag + "2"); return
        print("ERR create", name, s[:300]); return
    cid = ((r or {}).get("target_collaboration") or {}).get("id")
    print("CREATE", name, len(part), "->", cid, "invalid", r.get("invalid_open_id_list"), "conflicts", r.get("target_collaboration_conflicts"))
    if not cid: return
    d = go("GET", "202508/target_collaborations/" + cid); tc = d.get("target_collaboration", {})
    print("READBACK", cid, "invited", tc.get("creator_invited_count"), "rates", [(p["id"][-6:], p["commission"].get("rate")) for p in tc.get("products", [])], "sample", tc.get("free_sample_rule"), "msg_len", len(tc.get("message") or ""))
    created.append({"name": name, "id": cid, "n": len(part)})
    for x in part:
        ledger["sent"][x["open_id"]] = {"username": x["username"], "date": NOW.isoformat(), "collab": cid, "level": x["level"], "score": x.get("units"), "note": "linkshare 15%"}
def save_ledger(note):
    if created:
        ledger["runs"].append({"date": NOW.isoformat(), "created": created, "sent": sum(z["n"] for z in created), "note": note})
        json.dump(ledger, open(LEDGER, "w"), ensure_ascii=False, indent=1)

if BIG_ONLY:
    big = [x for x in json.load(open(BIGF)) if x["open_id"] not in excl]
    print("saved big list:", len(big))
    pick = []; used = collections.Counter()
    for x in big:
        lv = x["level"] or 0
        if cap.get(lv, -1) != -1 and used[lv] >= cap.get(lv, 0): continue
        used[lv] += 1; pick.append(x)
        if len(pick) >= CAP: break
    bad = set()
    for j in range(0, len(pick), 50):
        r = go("POST", "202605/target_collaborations/conflicts/check", b={"creator_open_id_list": [x["open_id"] for x in pick[j:j + 50]], "product_id_list": [SET8, BLACK5]})
        bad |= {z["creator_open_id"] for z in (r or {}).get("conflict_items", [])}
    pick = [x for x in pick if x["open_id"] not in bad]
    print("big to send:", len(pick), [x["username"] for x in pick])
    if not pick: print("nothing"); sys.exit(0)
    for i, part in enumerate([pick[j:j + 50] for j in range(0, len(pick), 50)]): create(part, "Big " + chr(65 + i))
    save_ledger("linkshare 15% level 7-8 after quota reset")
    print("DONE", created, "test accounts", test_accounts); sys.exit(0 if created else 4)

# ---- search: few followers, real sales ----
pool = {}
def search(body, pages, label):
    tok = None; sk = None; n0 = len(pool); page = -1
    for page in range(pages):
        qq = {"page_size": 20}
        if tok: qq["page_token"] = tok
        bb = dict(body)
        if sk: bb["search_key"] = sk
        r = go("POST", "202608/marketplace_creators/search", q=qq, b=bb)
        for x in r.get("creators", []):
            x.pop("avatar", None)
            if x["creator_open_id"] not in excl: pool.setdefault(x["creator_open_id"], x)
        tok = r.get("next_page_token"); sk = r.get("search_key") or sk
        if not tok: break
    print(f"search {label}: +{len(pool) - n0} (pages {page + 1})")
SALES = {"gmv_ranges": ["GMV_RANGE_1000_10000", "GMV_RANGE_10000_AND_ABOVE"], "units_sold_ranges": ["UNITS_SOLD_RANGE_100_1000", "UNITS_SOLD_RANGE_1000_AND_ABOVE"]}
for lo, hi in [(1, 300), (300, 1000), (1000, 2500), (2500, 5000)]:
    search({**SALES, "follower_demographics": {"count_range": {"count_ge": lo, "count_le": hi}}}, 20, f"fol {lo}-{hi}")
print("pool:", len(pool))
rows = []
for oid, x in pool.items():
    vg, lg, g = num(x.get("video_gmv")) or 0, num(x.get("live_gmv")) or 0, num(x.get("gmv")) or 0
    other = max(g - vg - lg, 0)
    rows.append((other, g, oid, x))
rows.sort(key=lambda r_: (-r_[0], -r_[1]))
short = rows[:ENRICH_N]
print("enriching", len(short))
cand = []
for other, g, oid, x in short:
    try:
        e = go("GET", "202608/marketplace_creators/" + oid, q={"data_groups": "BASIC_CREATOR_INFORMATION,CONTENT_PERFORMANCE,SALES_AND_GMV,COLLABORATION"})
    except Exception as ex:
        print("ERR detail", oid[-6:], str(ex)[:120]); continue
    e = e.get("creator", e)
    units = num(e.get("units_sold")) or 0
    dist = {z.get("content_type"): num(z.get("value")) or 0 for z in e.get("content_gmv_distribution", [])}
    vshare = dist.get("video_gmv", 0); lshare = dist.get("live_gmv", 0)
    vids = e.get("ec_video_count") or 0
    brands = e.get("brand_collaboration_count") or 0
    pr = e.get("product_original_price_range") or {}
    pmin, pmax = num(pr.get("minimum_amount")), num(pr.get("maximum_amount"))
    fol = x.get("follower_count") or 0
    lv = (x.get("creator_profile") or {}).get("creator_level")
    linkshare = units >= 50 and (vshare + lshare) <= 0.5 and vids <= 10 and brands >= 20
    cand.append({"open_id": oid, "username": x.get("username"), "level": lv, "followers": fol, "units": units, "gmv": g, "other_gmv": round(other), "vshare": round(vshare, 2), "lshare": round(lshare, 2),
                 "vids": vids, "brands": brands, "pmin": pmin, "pmax": pmax, "dist": dist, "ok": linkshare})
hits = [x for x in cand if x["ok"]]
print("enriched", len(cand), "link-share profile:", len(hits), "levels", dict(collections.Counter(x["level"] for x in hits)))
print("dist keys seen:", collections.Counter(k for x in cand for k in x["dist"]))
elig = {}
ids = [x["open_id"] for x in hits]
for i in range(0, len(ids), 100):
    r = go("POST", "202610/creator_outreach/eligibility/check", b={"creator_infos": [{"creator_open_id": z} for z in ids[i:i + 100]]})
    for e in (r or {}).get("creator_eligibility_results", []): elig[e["creator_open_id"]] = e
ok = []; drop = collections.Counter()
for x in hits:
    g = elig.get(x["open_id"])
    if not g: drop["no_elig"] += 1; continue
    if g.get("is_blocked") or g.get("is_connected") or g.get("is_paired"): drop["blocked/connected"] += 1; continue
    if not g.get("is_creator_follower_count_threshold_met"): drop["followers<min"] += 1; continue
    x["level"] = g.get("creator_level", x["level"]); x["quota_ok"] = bool(g.get("is_creator_level_quota_available")); ok.append(x)
ok.sort(key=lambda z: -z["units"])
print("eligible", len(ok), "dropped", dict(drop))
print(f"{'username':22} {'lvl':>3} {'fol':>5} {'units':>6} {'gmv$':>7} {'other$':>7} {'vsh':>4} {'lsh':>4} {'vids':>4} {'brands':>6} price$")
for x in ok:
    pr = f"{x['pmin']:.1f}-{x['pmax']:.1f}" if x["pmin"] is not None and x["pmax"] is not None else "-"
    print(f"{str(x['username']):22} {str(x['level']):>3} {x['followers']:>5} {int(x['units']):>6} {int(x['gmv']):>7} {x['other_gmv']:>7} {x['vshare']:>4} {x['lshare']:>4} {x['vids']:>4} {x['brands']:>6} {pr}")
small = [x for x in ok if (x["level"] or 0) < 7][:SMALL_CAP]
big = [x for x in ok if (x["level"] or 0) >= 7]
bad = set()
for j in range(0, len(small), 50):
    r = go("POST", "202605/target_collaborations/conflicts/check", b={"creator_open_id_list": [x["open_id"] for x in small[j:j + 50]], "product_id_list": [SET8, BLACK5]})
    bad |= {z["creator_open_id"] for z in (r or {}).get("conflict_items", [])}
small = [x for x in small if x["open_id"] not in bad]
print("levels 0-6 to send now:", len(small), "conflicts", len(bad), "| level 7-8 saved for after reset:", len(big))
json.dump([{k: v for k, v in x.items() if k != "dist"} for x in big], open(BIGF, "w"), ensure_ascii=False)
json.dump([{k: v for k, v in x.items() if k != "dist"} for x in ok], open("/tmp/linkshare_ok.json", "w"), ensure_ascii=False)
if not CREATE: print("DRY done"); sys.exit(0)
for i, part in enumerate([small[j:j + 50] for j in range(0, len(small), 50)]): create(part, "Link " + chr(65 + i))
save_ledger("linkshare 15% levels 0-6")
print("DONE", created, "test accounts", test_accounts)
