"""TT affiliate outreach (cron). Sends up to 100 target-collaboration invites per run, not more often than every MIN_DAYS.
Run inside worker:  python -I - [--dry-run] [--force] < affiliate_outreach.py
State: /app/data/affiliate/ledger.json (sent creators), logs: /app/data/affiliate/logs/<ts>.json, cats cache: /app/data/affiliate/cats.json
Rules (30.10.2026): set 8 pairs 25 %, black 5 pairs 20 %, 90 days, no free sample in invite (creators must chat), WhatsApp contact,
name <= 30 chars, <= 50 creators per collaboration, only creators with real sales (score threshold), never re-invite.
"""
import json, os, sys, time, datetime as dt, collections
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore

DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv
MIN_DAYS = 3
PER_RUN, PER_COLLAB = 100, 50
MIN_SCORE = 110.0
ENRICH_N = 220
SET8, BLACK5 = "1737926532373578823", "1736665360313713735"
PRODUCTS = [{"id": SET8, "target_commission_rate": 2500}, {"id": BLACK5, "target_commission_rate": 2000}]
CONTACT = {"whatsapp": "(+62) 85888014696"}
SAMPLE = {"has_free_sample": False, "is_sample_approval_exempt": False}
END_DAYS = 90
DATA = "/app/data/affiliate"
os.makedirs(f"{DATA}/logs", exist_ok=True)
J = dt.timezone(dt.timedelta(hours=7))
NOW = dt.datetime.now(J)
MSG_DEFAULT = (
    "Halo Kak! Kami LOMIRA, brand kaos kaki katun premium (85% katun, adem, anti bau), sudah terjual ribuan pasang di TikTok Shop.\n\n"
    "Komisi spesial untuk Kakak:\n"
    "Paket 8 Pasang Kaos Kaki Hitam (Rp99.000): komisi 25%, sekitar Rp24.700 per paket.\n"
    "Kaos Kaki Hitam 5 Pasang (Rp62.900): komisi 20%, sekitar Rp12.500 per paket.\n\n"
    "Produk cepat laku, cocok untuk konten OOTD, daily style, dan olahraga. Stok ready, kirim cepat.\n"
    "Sampel gratis untuk kreator terpilih yang serius promosi, chat kami ya.\n"
    "Tambahkan ke showcase dan mulai cuan hari ini!")
MSG = open(f"{DATA}/invite_text.txt", encoding="utf-8").read().strip() if os.path.exists(f"{DATA}/invite_text.txt") else MSG_DEFAULT
MEN_TOP = {"824328"}
STRONG_TOP = {"601352", "603014", "605248"}
FASHION_TOP = MEN_TOP | STRONG_TOP | {"601152", "601303", "802184", "824584"}
KEYWORDS = ["kaos kaki", "socks", "fashion pria", "outfit pria", "ootd", "sneakers", "sepatu", "olahraga", "gym", "fashion", "style",
            "cowok", "pria", "lari", "futsal", "padel", "bapak", "ayah", "cewek", "hijab", "distro", "streetwear", "kemeja", "celana",
            "hoodie", "jaket", "sandal", "tas", "grosir", "murah", "hemat", "daily", "kantor", "sekolah", "santai", "spill", "racun", "review"]
FOLLOWER_RANGES = [(5000, 20000), (20000, 50000), (50000, 100000), (100000, 300000), (300000, 1000000), (1000000, 20000000)]

t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"), settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t, shop_cipher=settings.tiktok_shop_shop_cipher or None)
A = "/affiliate_seller/"
log = {"started": NOW.isoformat(), "dry_run": DRY, "steps": []}

def say(*a):
    s = " ".join(str(x) for x in a)
    print(NOW.strftime("%d.%m %H:%M"), s, flush=True); log["steps"].append(s[:400])

def go(m, p, q=None, b=None, full=False):
    for i in range(5):
        try:
            r = c.request(m, (p if full else A + p), query=q, body=b, resource="affiliate_outreach"); time.sleep(1.2); return r
        except Exception as e:
            s = str(e)
            if "36009002" in s or "429" in s or "45101004" in s:
                time.sleep(10 * (i + 1)); continue
            say("ERR", p, s[:200]); time.sleep(1.2); return None
    say("ERR rate limit", p); return None

def num(v):
    try:
        return float(v["amount"]) if isinstance(v, dict) else float(v)
    except (TypeError, ValueError, KeyError):
        return None

def finish(status):
    log["finished"] = dt.datetime.now(J).isoformat(); log["status"] = status
    json.dump(log, open(f"{DATA}/logs/{NOW.strftime('%Y%m%d_%H%M')}{'_dry' if DRY else ''}.json", "w"), ensure_ascii=False, indent=1)
    say("DONE", status)

# ---- 0. gate ----
ledger = json.load(open(f"{DATA}/ledger.json")) if os.path.exists(f"{DATA}/ledger.json") else {"sent": {}, "last_sent": None, "runs": []}
if ledger.get("last_sent") and not FORCE and not DRY:
    last = dt.datetime.fromisoformat(ledger["last_sent"])
    if (NOW - last) < dt.timedelta(days=MIN_DAYS, hours=-2):
        say(f"skip: last send {last.strftime('%d.%m %H:%M')}, next after {(last + dt.timedelta(days=MIN_DAYS)).strftime('%d.%m %H:%M')}"); finish("skipped"); sys.exit(0)
say("start", "DRY" if DRY else "LIVE", "already sent:", len(ledger["sent"]))

# ---- 1. quota ----
q = go("GET", "202607/creator_outreach/quota")
if not q:
    finish("no quota data"); sys.exit(1)
qd = q["data"]
cap = {}
for d in qd["quota_details"]:
    rem = -1 if d["quota_period_sum"] == -1 else max(0, d["quota_period_sum"] - d["quota_period_use"] - 2)
    for lv in d["creator_levels"]: cap[lv] = rem
say("quota use", qd.get("quota_use"), "remaining by level:", {k: v for k, v in cap.items() if k in (2, 4, 6, 8)})

# ---- 2. exclusions ----
excl = set(ledger["sent"])
r = go("POST", "202508/target_collaborations/search", q={"page_size": 20}, b={"collaboration_status": "ONGOING"})
for x in (r or {}).get("target_collaborations", []):
    d = go("GET", "202508/target_collaborations/" + x["id"])
    for cr in (d or {}).get("target_collaboration", {}).get("creators", []):
        excl.add(cr["creator_open_id"])
say("excluded (ledger + ongoing collabs):", len(excl))

# ---- 3. categories ----
cpath = f"{DATA}/cats.json"
if os.path.exists(cpath) and (time.time() - os.path.getmtime(cpath)) < 30 * 86400:
    cats = json.load(open(cpath))
else:
    cats = {}
    r = go("GET", "/product/202309/categories", q={"locale": "id-ID"}, full=True)
    for x in (r or {}).get("categories", []): cats[x["id"]] = {"parent": x.get("parent_id")}
    if cats: json.dump(cats, open(cpath, "w"))
def top(cid):
    c_ = cats.get(cid); n = 0
    while c_ and c_["parent"] not in ("0", None, "") and n < 6:
        cid = c_["parent"]; c_ = cats.get(cid); n += 1
    return cid

# ---- 4. search ----
pool = {}
def search(body, pages, label, page_size=20):
    tok = None; sk = None; n0 = len(pool); page = -1
    for page in range(pages):
        qq = {"page_size": page_size}
        if tok: qq["page_token"] = tok
        bb = dict(body)
        if sk: bb["search_key"] = sk
        r = go("POST", "202608/marketplace_creators/search", q=qq, b=bb)
        if not r: break
        for x in r.get("creators", []):
            x.pop("avatar", None)
            if x["creator_open_id"] not in excl: pool.setdefault(x["creator_open_id"], x)
        tok = r.get("next_page_token"); sk = r.get("search_key") or sk
        if not tok: break
    say(f"search {label}: +{len(pool) - n0} (pages {page + 1})")
GMV = {"gmv_ranges": ["GMV_RANGE_100_1000", "GMV_RANGE_1000_10000", "GMV_RANGE_10000_AND_ABOVE"],
       "units_sold_ranges": ["UNITS_SOLD_RANGE_10_100", "UNITS_SOLD_RANGE_100_1000", "UNITS_SOLD_RANGE_1000_AND_ABOVE"]}
for lo, hi in FOLLOWER_RANGES:
    search({**GMV, "follower_demographics": {"count_range": {"count_ge": lo, "count_le": hi}}}, 20, f"followers {lo}-{hi}")
run_idx = len(ledger["runs"])
kws = KEYWORDS[(run_idx * 10) % len(KEYWORDS):] + KEYWORDS[:(run_idx * 10) % len(KEYWORDS)]
for kw in kws[:12]:
    search({"keyword": kw, "follower_demographics": {"count_range": {"count_ge": 5000, "count_le": 20000000}}}, 2, f"kw {kw!r}")
say("pool after exclusions:", len(pool))

# ---- 5. rank ----
rows = []
for oid, x in pool.items():
    fo = x.get("follower_count") or 0
    if fo < 5000: continue
    vg, lg, g = num(x.get("video_gmv")) or 0, num(x.get("live_gmv")) or 0, num(x.get("gmv")) or 0
    vv = x.get("avg_ec_video_view_count") or 0
    tops = {top(c_) for c_ in x.get("category_ids", [])}
    men, strong, fash = len(tops & MEN_TOP), len(tops & STRONG_TOP), len(tops & FASHION_TOP)
    s = min(vg, 5000) / 100 + min(lg, 5000) / 400 + min(vv, 20000) / 1000 + 20 * men + 10 * min(strong, 2) + 5 * min(fash, 2)
    if vg == 0 and lg == 0 and g == 0 and vv < 1000: s -= 30
    rows.append([s, oid, x, vg, lg, vv, fo])
rows.sort(key=lambda r_: -r_[0])
# shortlist balanced by level quota: do not fill it with level 7-8 when their weekly quota is (almost) gone
big_cap = cap.get(7, -1)
big_max = ENRICH_N if big_cap == -1 else min(ENRICH_N, big_cap + 40)
short, nbig = [], 0
for r_ in rows:
    lv = (r_[2].get("creator_profile") or {}).get("creator_level") or 0
    if lv >= 7:
        if nbig >= big_max: continue
        nbig += 1
    short.append(r_)
    if len(short) >= ENRICH_N: break
say("ranked", len(rows), "shortlist", len(short), "of which level 7-8:", nbig, "(cap", big_max, ")")

# ---- 6. enrich + eligibility ----
cand = []
for s, oid, x, vg, lg, vv, fo in short:
    e = go("GET", "202608/marketplace_creators/" + oid, q={"data_groups": "BASIC_CREATOR_INFORMATION,CONTENT_PERFORMANCE,SALES_AND_GMV,COLLABORATION"})
    if not e: continue
    e = e.get("creator", e)
    units = num(e.get("units_sold"))
    pr = e.get("product_original_price_range") or {}
    pmin, pmax = num(pr.get("minimum_amount")), num(pr.get("maximum_amount"))
    vshare = next((num(z["value"]) for z in e.get("content_gmv_distribution", []) if z.get("content_type") == "video_gmv"), None) or 0.0
    catd = {z["category_id"]: num(z["value"]) or 0.0 for z in e.get("category_gmv_distribution", [])}
    fit = sum(v for k, v in catd.items() if k in ("824328", "603014", "601352", "605248"))
    fit_any = fit + sum(v for k, v in catd.items() if k in ("601152", "601303", "802184", "824584"))
    vids = e.get("ec_video_count") or 0
    b = 0.0
    if units is not None:
        b += -30 if units <= 0 else (12 if units >= 1000 else 8 if units >= 100 else 3 if units >= 10 else 0)
    if pmin is not None and pmax is not None:
        b += -15 if (pmax < 2.0 or pmin > 25.0) else (8 if (pmin <= 6.2 and pmax >= 3.8) else 0)
    b += 25 * min(fit, 1.0) + 8 * min(fit_any, 1.0)
    if fit_any < 0.05 and catd: b -= 15
    b += 10 * min(vshare, 0.6) / 0.6
    b += -10 if vids == 0 else (4 if vids >= 10 else 0)
    cand.append({"open_id": oid, "username": x.get("username"), "level": (x.get("creator_profile") or {}).get("creator_level"), "score": round(s + b, 1),
                 "units": units, "pmin": pmin, "pmax": pmax, "fit": round(fit, 2), "vshare": round(vshare, 2), "vids": vids, "video_gmv": round(vg), "followers": fo})
elig = {}
ids = [x["open_id"] for x in cand]
for i in range(0, len(ids), 100):
    r = go("POST", "202610/creator_outreach/eligibility/check", b={"creator_infos": [{"creator_open_id": z} for z in ids[i:i + 100]]})
    for e in (r or {}).get("creator_eligibility_results", []): elig[e["creator_open_id"]] = e
ok = []
drop = collections.Counter()
for x in cand:
    g = elig.get(x["open_id"])
    if not g: drop["no_elig"] += 1; continue
    if g.get("is_blocked") or g.get("is_connected") or g.get("is_paired"): drop["blocked/connected"] += 1; continue
    if not g.get("is_creator_follower_count_threshold_met") or not g.get("is_creator_level_quota_available"): drop["threshold/quota"] += 1; continue
    if x["score"] < MIN_SCORE: drop["low_score"] += 1; continue
    x["level"] = g.get("creator_level", x["level"]); ok.append(x)
ok.sort(key=lambda z: -z["score"])
say("candidates", len(cand), "eligible+score", len(ok), "dropped", dict(drop))

# ---- 7. pick within per-level quota, conflicts ----
used = collections.Counter(); pick = []
for x in ok:
    lv = x["level"] if x["level"] is not None else 0
    if cap.get(lv, -1) != -1 and used[lv] >= cap.get(lv, 0): continue
    used[lv] += 1; pick.append(x)
    if len(pick) >= PER_RUN + 10: break
bad = set()
for j in range(0, len(pick), 50):   # API accepts at most 50 creators per conflict check
    conf = go("POST", "202605/target_collaborations/conflicts/check", b={"creator_open_id_list": [x["open_id"] for x in pick[j:j + 50]], "product_id_list": [SET8, BLACK5]})
    bad |= {z["creator_open_id"] for z in (conf or {}).get("conflict_items", [])}
pick = [x for x in pick if x["open_id"] not in bad][:PER_RUN]
say("picked", len(pick), "levels", dict(collections.Counter(x["level"] for x in pick)), "conflicts dropped", len(bad))
log["picked"] = pick
for x in pick[:PER_RUN]:
    print(f"   {x['score']:6.1f} L{x['level']} units={x['units']} fit={x['fit']} vshare={x['vshare']} vids={x['vids']} video$={x['video_gmv']} fol={x['followers']} {x['username']}")
if len(pick) < 10:
    finish("too few candidates, nothing sent"); sys.exit(0)
if DRY:
    finish("dry run, nothing sent"); sys.exit(0)

# ---- 8. create ----
END = str(int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=END_DAYS)).timestamp()))
tag = NOW.strftime("%d%b")
created = []
for i, part in enumerate([pick[j:j + PER_COLLAB] for j in range(0, len(pick), PER_COLLAB)]):
    name = f"Lomira Komisi 25 {tag} {chr(65 + i)}"[:30]
    body = {"name": name, "message": MSG, "end_time": END, "products": PRODUCTS, "creator_user_open_ids": [x["open_id"] for x in part],
            "seller_contact_info": CONTACT, "free_sample_rule": SAMPLE, "preferred_content_type": "VIDEO"}
    r = go("POST", "202508/target_collaborations", b=body)
    cid = ((r or {}).get("target_collaboration") or {}).get("id")
    say("create", name, "->", cid, "invalid", (r or {}).get("invalid_open_id_list"), "conflicts", (r or {}).get("target_collaboration_conflicts"))
    if not cid: continue
    d = go("GET", "202508/target_collaborations/" + cid)
    tc = (d or {}).get("target_collaboration", {})
    say("readback", cid, "invited", tc.get("creator_invited_count"), "rates", [(p["id"][-6:], p["commission"].get("rate")) for p in tc.get("products", [])])
    created.append({"name": name, "id": cid, "n": len(part)})
    stamp = NOW.isoformat()
    for x in part:
        ledger["sent"][x["open_id"]] = {"username": x["username"], "date": stamp, "collab": cid, "level": x["level"], "score": x["score"]}
if created:
    ledger["last_sent"] = NOW.isoformat()
    ledger["runs"].append({"date": NOW.isoformat(), "created": created, "sent": sum(z["n"] for z in created)})
    json.dump(ledger, open(f"{DATA}/ledger.json", "w"), ensure_ascii=False, indent=1)
log["created"] = created
finish(f"sent {sum(z['n'] for z in created)} in {len(created)} collaborations")
