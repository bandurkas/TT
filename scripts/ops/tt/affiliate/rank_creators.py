import json, sys, collections
D = "/private/tmp/claude-501/-Users-styserg/fc1ed73b-7b34-4069-a3e4-0190be1efa3e/scratchpad"
cats = json.load(open(f"{D}/cats.json"))
invited = json.load(open(f"{D}/invited.json"))
pool = {}
for p in "ABCDE":
    try:
        for x in json.load(open(f"{D}/pool_{p}.json")):
            oid = x["creator_open_id"]
            if oid not in pool:
                pool[oid] = x; x["_pools"] = ""
            pool[oid]["_pools"] += p
    except FileNotFoundError:
        pass
print("pool total", len(pool), "invited", len(invited))

def top(cid):
    c = cats.get(cid)
    seen = 0
    while c and c["parent"] not in ("0", None, "") and seen < 6:
        cid = c["parent"]; c = cats.get(cid); seen += 1
    return cid

def cname(cid):
    return (cats.get(cid) or {}).get("name") or cid

MEN_TOP = {"824328"}                                   # Pakaian & Dalaman Pria
STRONG_TOP = {"601352", "603014", "605248"}            # Sepatu, Olahraga & Outdoor, Aksesori Pakaian
FASHION_TOP = MEN_TOP | STRONG_TOP | {"601152", "601303", "802184", "824584"}  # + Wanita, Muslim Fashion, Anak, Koper & Tas

def amt(x, k):
    v = x.get(k)
    try:
        return float(v["amount"]) if isinstance(v, dict) else 0.0
    except (TypeError, ValueError, KeyError):
        return 0.0

rows = []
for oid, x in pool.items():
    if oid in invited:
        continue
    fo = x.get("follower_count") or 0
    if fo < 5000:
        continue
    vg, lg, g = amt(x, "video_gmv"), amt(x, "live_gmv"), amt(x, "gmv")
    vv = x.get("avg_ec_video_view_count") or 0
    lvl = (x.get("creator_profile") or {}).get("creator_level")
    tops = {top(c) for c in x.get("category_ids", [])}
    fash = len(tops & FASHION_TOP); men = len(tops & MEN_TOP); strong = len(tops & STRONG_TOP)
    score = 0.0
    score += min(vg, 5000) / 100          # up to 50
    score += min(lg, 5000) / 400          # up to 12.5
    score += min(vv, 20000) / 1000        # up to 20
    score += 20 * men + 10 * min(strong, 2) + 5 * min(fash, 2)
    if vg == 0 and lg == 0 and g == 0 and vv < 1000:
        score -= 30
    rows.append((score, oid, x, vg, lg, vv, fo, lvl, [cname(c) for c in x.get("category_ids", [])][:3], men, fash))
rows.sort(key=lambda r: -r[0])
print("candidates", len(rows))
json.dump([{"open_id": r[1], "username": r[2].get("username"), "nickname": r[2].get("nickname"), "score": round(r[0], 1), "video_gmv": r[3], "live_gmv": r[4], "vid_views": r[5], "followers": r[6], "level": r[7], "cats": r[8], "men": r[9], "fash": r[10], "pools": r[2].get("_pools")} for r in rows], open(f"{D}/ranked.json", "w"), ensure_ascii=False, indent=0)
print(f"{'score':>6} {'lvl':>3} {'followers':>9} {'video$':>7} {'live$':>7} {'views':>6} men fash username / cats")
for r in rows[:int(sys.argv[1]) if len(sys.argv) > 1 else 60]:
    print(f"{r[0]:6.1f} {str(r[7]):>3} {r[6]:>9} {r[3]:7.0f} {r[4]:7.0f} {r[5]:>6} {r[9]:>3} {r[10]:>4} {r[2].get('username')} / {', '.join(r[8])}")
print("level dist top150:", collections.Counter(r[7] for r in rows[:150]))
