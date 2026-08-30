"""Deterministic findings for Zones 2 & 6 (SPEC §43, §47): analytics first, each with evidence +
confidence. No LLM; wording is templated. Impact figures are estimates unless marked measured."""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from src.domain.dashboard.compute import ZERO, Totals, pct_change

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"


def _f(key: str, severity: str, title: str, detail: str, impact: Decimal | None, confidence: str,
       source: str, measured: bool, links: dict[str, Any] | None = None, kind: str = "risk") -> dict[str, Any]:
    return {"key": key, "kind": kind, "severity": severity, "title": title, "detail": detail,
            "impact": impact, "confidence": confidence, "source": source, "measured": measured,
            "links": links or {}}


def findings(cur: Totals, prev: Totals, floor: Decimal, products: Sequence[dict[str, Any]],
             videos: Sequence[dict[str, Any]], funnel: dict[str, Any], min_orders: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # 1. ads vs break-even
    roas, be = cur.blended_roas, cur.break_even_roas
    if roas is not None and be is not None and cur.ad_cost > 0:
        if roas < be:
            loss = (cur.ad_cost - cur.contribution) if cur.contribution < cur.ad_cost else ZERO
            out.append(_f("ads_below_break_even", "CRITICAL",
                          f"GMV Max spend above break-even: blended ROAS {roas} < {be}",
                          f"Ad deductions {cur.ad_cost} vs contribution before ads {cur.contribution}. "
                          "Ad cost is the shop-level payout deduction (BLENDED, LOW confidence); "
                          "per-campaign split needs the Ads API.",
                          -loss, LOW, "payout deductions + statements", False,
                          {"tab": "campaigns"}))
        else:
            out.append(_f("ads_above_break_even", "INFO",
                          f"Blended ROAS {roas} ≥ break-even {be}",
                          f"Contribution before ads {cur.contribution} covers ad deductions {cur.ad_cost}; "
                          f"net profit {cur.net_profit}.", cur.net_profit, LOW,
                          "payout deductions + statements", False, {"tab": "campaigns"}, kind="opportunity"))
    # 2. margin vs floor
    m = cur.net_margin
    if m is not None and m < floor and cur.orders >= min_orders:
        out.append(_f("margin_below_floor", "WARNING", f"Net margin {m:.1%} below floor {floor:.0%}",
                      f"{cur.orders} orders, net profit {cur.net_profit} on net revenue "
                      f"{cur.net_seller_revenue}.", cur.net_profit, MEDIUM, "analytics_shop_daily",
                      cur.provisional_orders == 0))
    # 3. refunds
    rr = cur.refund_rate
    if rr is not None and rr >= Decimal("0.10") and cur.orders >= min_orders:
        out.append(_f("refund_rate_high", "WARNING",
                      f"Refund rate {rr:.1%} — {cur.refunded_orders} of {cur.orders} orders",
                      f"Refunded value {cur.refunds}; fees on refunded orders are usually kept by TikTok.",
                      -cur.refunds, HIGH, "statements", True, {"tab": "products"}))
    # 4. funnel deterioration
    diag = funnel.get("diagnosis")
    if diag:
        out.append(_f("funnel_deterioration", "WARNING",
                      f"Largest drop: {diag['stage_from']} → {diag['stage_to']} "
                      f"{diag['current_rate']:.2%} vs baseline {diag['baseline_rate']:.2%} "
                      f"({diag['delta_pct']:+.1%})",
                      "; ".join(diag["evidence"]) or "conversion below the previous comparable period",
                      diag.get("lost_profit"), MEDIUM, "video_metrics + analytics_order_profit", False,
                      {"zone": "funnel"}))
    # 5. losing products
    for p in products:
        if p["status"] == "REDUCE":
            out.append(_f(f"product_loss:{p['product_id']}", "WARNING",
                          f"{p['title']}: net loss {p['net_profit']} on {p['orders']} orders",
                          p["status_reason"] + "; ad cost is a blended estimate.", p["net_profit"], LOW,
                          "analytics_product_daily", False, {"product_id": p["product_id"]}))
    # 6. video opportunities / leaks
    for v in videos:
        if v["classification"] in ("WINNER", "PROMISING"):
            out.append(_f(f"video_{v['classification'].lower()}:{v['video_id']}", "OPPORTUNITY",
                          f"Video {v['external_video_id']}: {v['classification']} — CTR {v['ctr']}, "
                          f"{v['orders']} orders, GMV {v['gmv']}",
                          "; ".join(v["reasons"]), v["gmv"], v["confidence"], "video_metrics", True,
                          {"video_id": v["video_id"]}, kind="opportunity"))
        elif v["classification"] == "TRAFFIC_NO_SALES":
            out.append(_f(f"video_traffic_no_sales:{v['video_id']}", "INFO",
                          f"Video {v['external_video_id']}: traffic without sales ({v['clicks']} clicks)",
                          "; ".join(v["reasons"]), None, v["confidence"], "video_metrics", True,
                          {"video_id": v["video_id"]}))
    # 7. period comparison headline
    ch = pct_change(cur.net_profit, prev.net_profit)
    if ch is not None:
        out.append(_f("profit_vs_previous", "INFO", f"Net profit {ch:+.1%} vs previous period",
                      f"{cur.net_profit} now vs {prev.net_profit} before.", cur.net_profit - prev.net_profit,
                      MEDIUM if cur.provisional_orders == 0 else LOW, "analytics_shop_daily",
                      cur.provisional_orders == 0))
    rank = {"CRITICAL": 0, "WARNING": 1, "OPPORTUNITY": 2, "INFO": 3}
    out.sort(key=lambda f: (rank.get(f["severity"], 9), -abs(f["impact"] or ZERO)))
    return out
