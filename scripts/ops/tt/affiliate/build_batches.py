import json, sys, collections
D = "/private/tmp/claude-501/-Users-styserg/fc1ed73b-7b34-4069-a3e4-0190be1efa3e/scratchpad"
R = {r["open_id"]: r for r in json.load(open(f"{D}/ranked.json"))}
E = json.load(open(f"{D}/enriched.json"))
G = json.load(open(f"{D}/elig.json"))
BIG_QUOTA = int(sys.argv[1]) if len(sys.argv) > 1 else 70   # level 7-8 cap for this batch
TOTAL = 100

def num(v):
    try:
        return float(v["amount"]) if isinstance(v, dict) else float(v)
    except (TypeError, ValueError, KeyError):
        return None

rows = []
drop = collections.Counter()
for oid, r in R.items():
    if oid not in E:
        continue
    e = E[oid]; g = G.get(oid)
    if "_err" in e:
        drop["enrich_err"] += 1; continue
    if not g:
        drop["no_elig"] += 1; continue
    if g.get("is_blocked"):
        drop["blocked"] += 1; continue
    if g.get("is_connected") or g.get("is_paired"):
        drop["already_connected"] += 1; continue
    if not g.get("is_creator_follower_count_threshold_met"):
        drop["follower_threshold"] += 1; continue
    if not g.get("is_creator_level_quota_available"):
        drop["no_quota"] += 1; continue
    units = num(e.get("units_sold"))
    pr = e.get("product_original_price_range") or {}
    pmin, pmax = num(pr.get("minimum_amount")), num(pr.get("maximum_amount"))   # USD
    vshare = next((num(x["value"]) for x in e.get("content_gmv_distribution", []) if x.get("content_type") == "video_gmv"), None) or 0.0
    catd = {x["category_id"]: num(x["value"]) or 0.0 for x in e.get("category_gmv_distribution", [])}
    fit = sum(v for k, v in catd.items() if k in ("824328", "603014", "601352", "605248"))
    fit_any = fit + sum(v for k, v in catd.items() if k in ("601152", "601303", "802184", "824584"))
    vids = e.get("ec_video_count") or 0
    pps = e.get("avg_commission_rate"); ful = e.get("post_rate")
    lvl = g.get("creator_level") if g.get("creator_level") is not None else r["level"]
    bonus = 0.0
    if units is not None:
        if units <= 0: bonus -= 30
        elif units >= 1000: bonus += 12
        elif units >= 100: bonus += 8
        elif units >= 10: bonus += 3
    if pmin is not None and pmax is not None:
        if pmax < 2.0 or pmin > 25.0: bonus -= 15          # only very cheap or only expensive items
        elif pmin <= 6.2 and pmax >= 3.8: bonus += 8        # our 62 900 / 99 000 IDR = $3.9 / $6.1 inside their range
    bonus += 25 * min(fit, 1.0) + 8 * min(fit_any, 1.0)     # what they actually sell
    if fit_any < 0.05 and catd: bonus -= 15                  # sells only unrelated categories
    bonus += 10 * min(vshare, 0.6) / 0.6                     # video-driven sales
    if vids == 0: bonus -= 10
    elif vids >= 10: bonus += 4
    rows.append({"open_id": oid, "username": r["username"], "level": lvl, "score": r["score"] + bonus, "base": r["score"], "units": units, "pmin": pmin, "pmax": pmax, "fit": round(fit, 2), "fit_any": round(fit_any, 2), "vshare": round(vshare, 2), "vids": vids, "pps": pps, "ful": ful, "video_gmv": r["video_gmv"], "live_gmv": r["live_gmv"], "views": r["vid_views"], "followers": r["followers"], "cats": r["cats"]})
rows.sort(key=lambda x: -x["score"])
print("eligible", len(rows), "dropped", dict(drop))
big = [x for x in rows if (x["level"] or 0) >= 7]
small = [x for x in rows if (x["level"] or 0) < 7]
pick = big[:BIG_QUOTA] + small[:TOTAL - min(len(big), BIG_QUOTA)]
if len(pick) < TOTAL:
    extra = [x for x in big[BIG_QUOTA:] if x not in pick][:TOTAL - len(pick)]
    pick += extra
pick = pick[:TOTAL]
print("picked", len(pick), "levels", dict(collections.Counter(x["level"] for x in pick)))
print(f"{'score':>6} {'lvl':>3} {'units':>6} {'price$':>9} {'fit':>4} {'vshr':>4} {'vids':>4} {'video$':>7} {'followers':>9} username")
for x in pick:
    pr = f"{x['pmin']:.1f}-{x['pmax']:.1f}" if x["pmin"] is not None and x["pmax"] is not None else "-"
    print(f"{x['score']:6.1f} {str(x['level']):>3} {str(int(x['units'])) if x['units'] is not None else '-':>6} {pr:>9} {x['fit']:>4} {x['vshare']:>4} {x['vids']:>4} {x['video_gmv']:7.0f} {x['followers']:>9} {x['username']}")
ids = [x["open_id"] for x in pick]
batches = {"dry_run": True, "batches": [
    {"name": "LOMIRA Kaos Kaki - Komisi 25% - Okt 2026 - test", "open_ids": ids[:1]},
    {"name": "LOMIRA Kaos Kaki - Komisi 25% - Okt 2026 - 1A", "open_ids": ids[1:50]},
    {"name": "LOMIRA Kaos Kaki - Komisi 25% - Okt 2026 - 1B", "open_ids": ids[50:100]},
]}
json.dump(batches, open(f"{D}/batches.json", "w"), ensure_ascii=False, indent=1)
json.dump(pick, open(f"{D}/picked.json", "w"), ensure_ascii=False, indent=0)
print("batches:", [len(b["open_ids"]) for b in batches["batches"]])
