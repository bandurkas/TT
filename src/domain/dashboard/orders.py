"""Read-only order ledger. Monetary values come from versioned profit rows, not shop GMV."""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from src.analytics.transaction_types import NormalizedType, revenue_effect

ZERO = Decimal(0)
FIELDS = ("sale_proceeds", "seller_discounts", "refunds", "platform_fees", "affiliate_commission",
          "seller_shipping", "taxes", "subsidies", "adjustments", "net_seller_revenue", "cogs",
          "packaging", "inbound_logistics", "other_variable", "contribution_profit",
          "allocated_ad_cost", "estimated_net_profit")
COSTS = ("cogs", "packaging", "inbound_logistics", "other_variable")
FEES = ("platform_fees", "affiliate_commission", "seller_shipping", "taxes")
FINAL_STATUSES = ("SETTLED", "PAID", "REFUNDED", "ADJUSTED")
TXN_GROUP = {
    "SALE_PROCEEDS": "sale_proceeds", "SELLER_DISCOUNT": "seller_discounts",
    "REFUND": "refunds", "PLATFORM_COMMISSION": "platform_fees", "SERVICE_FEE": "platform_fees",
    "TRANSACTION_FEE": "platform_fees", "AFFILIATE_COMMISSION": "affiliate_commission",
    "SHIPPING_FEE": "seller_shipping", "TAX": "taxes", "PLATFORM_SUBSIDY": "subsidies",
    "SHIPPING_ADJUSTMENT": "adjustments", "REFUND_FEE_ADJUSTMENT": "adjustments",
    "OTHER_ADJUSTMENT": "adjustments",
}


def dec(v: Any) -> Decimal:
    return ZERO if v is None else Decimal(str(v))


def share(amount: Decimal, base: Decimal) -> Decimal | None:
    return (amount / base).quantize(Decimal("0.000001")) if base > ZERO else None


def amounts(p: Any) -> dict[str, Decimal]:
    return {key: dec(getattr(p, key, None)) for key in FIELDS}


def financial_state(p: Any | None) -> str:
    if p is None:
        return "not_calculated"
    return "final" if (p.profit_status in FINAL_STATUSES and
                       (p.inputs_snapshot or {}).get("source") == "settled") else "preliminary"


def inputs_known(p):
    snap = p.inputs_snapshot or {}
    return not ((snap.get("cogs_missing") and not snap.get("cogs_default_used")) or
                (snap.get("source") == "ratio_estimate" and snap.get("fee_ratio") is None) or
                snap.get("mismatch"))


def compact(v: dict[str, Decimal]) -> dict[str, Any]:
    base = v["sale_proceeds"] - v["seller_discounts"]
    out = {"revenue_base": base, "fees": sum((v[k] for k in FEES), ZERO),
            "costs": sum((v[k] for k in COSTS), ZERO), "refunds": v["refunds"],
            "other_effect": v["subsidies"] + v["adjustments"] - v["refunds"],
            "ad_cost": v["allocated_ad_cost"], "net_profit": v["estimated_net_profit"],
            "profit_share": share(v["estimated_net_profit"], base)}
    out["shares"] = {k: share(out[k], base) for k in ("fees", "costs", "refunds", "other_effect", "ad_cost", "net_profit")}
    return out


def order_row(order: Any, p: Any | None, items: list[dict[str, Any]]) -> dict[str, Any]:
    snap = p.inputs_snapshot or {} if p else {}
    unconfirmed = []
    if p and snap.get("source") == "ratio_estimate" and snap.get("fee_ratio") is None:
        unconfirmed.append("fees")
    if p and snap.get("cogs_missing") and not snap.get("cogs_default_used"):
        unconfirmed.append("costs")
    if p and not snap.get("ad_cost_known"):
        unconfirmed.append("ad_cost")
    if unconfirmed or p and not inputs_known(p):
        unconfirmed.append("net_profit")
    money = compact(amounts(p)) if p else None
    if money:
        for key in unconfirmed:
            money[key] = None
            money["shares"][key] = None
        if "net_profit" in unconfirmed:
            money["profit_share"] = None
    return {"id": order.id, "external_order_id": order.external_order_id,
            "created_at": order.order_created_at, "order_status": order.order_status,
            "currency": p.currency if p else order.currency, "state": financial_state(p),
            "profit_status": p.profit_status if p else None,
            "version": p.version if p else None, "calculated_at": p.calculated_at if p else None,
            "items": items, "unconfirmed_fields": unconfirmed, "amounts": money,
            "ad_cost_partial": bool(snap.get("ad_cost_partial"))}


def statement_ids(p: Any) -> list[str]:
    txns = (p.inputs_snapshot or {}).get("txns", [])
    return sorted({str(t[3]) for t in txns if len(t) == 4 and t[3]})


def breakdown(order: Any, p: Any | None, items: list[dict[str, Any]],
              records: Sequence[Any]) -> dict[str, Any]:
    out = order_row(order, p, items)
    out.update(lines=[], transactions=[], settlements=[], warnings=[], calculation_check=None,
               settlement_check={"status": "unavailable", "difference": None, "actual": None})
    if p is None:
        out["warnings"] = ["not_calculated"]
        return out
    v, snap = amounts(p), p.inputs_snapshot or {}
    base = v["sale_proceeds"] - v["seller_discounts"]
    state = financial_state(p)
    source = snap.get("source", "unknown")
    evidence = "final" if state == "final" and source == "settled" else (
        "preliminary" if source == "unsettled_record" else "estimate" if source == "ratio_estimate" else "unavailable")
    costs_state = "estimate" if snap.get("cogs_default_used") else "unavailable" if snap.get("cogs_missing") else "internal"
    for flag in ("cogs_missing", "cogs_default_used", "mismatch"):
        if snap.get(flag):
            out["warnings"].append(flag)
    if source == "ratio_estimate" and snap.get("fee_ratio") is None:
        out["warnings"].append("fees_unknown_zero_assumption")
    out["warnings"].append("advertising_allocated")
    if not snap.get("ad_cost_known"):
        out["warnings"].append("advertising_missing")
    elif snap.get("ad_cost_partial"):
        out["warnings"].append("advertising_partial")
    out["basis"] = "revenue_after_seller_discount_before_refunds_and_fees"
    out["revenue_base"] = base
    out["source"] = source
    out["ad_method"] = p.attribution_method
    out["ad_confidence"] = p.attribution_confidence
    out["ad_window_days"] = snap.get("ad_window_days")
    out["cost_versions"] = [{"sku_id": str(sku), "effective_from": str(day), "cogs_per_unit": dec(cost),
                             "evidence": costs_state if str(day) == "1970-01-01" else "internal"}
                            for sku, day, cost in snap.get("cost_versions", [])]
    transactions = []
    for tx in snap.get("txns", []):
        if len(tx) != 4:
            continue
        txid, kind, value, sid = tx
        try:
            effect = revenue_effect(NormalizedType(kind), dec(value))
        except ValueError:
            effect = ZERO
        transactions.append({"id": str(txid), "field": str(txid).rsplit(":", 1)[-1],
                             "kind": kind, "group": TXN_GROUP.get(kind, "unknown"),
                             "amount": effect, "raw_amount": dec(value), "share": share(effect, base),
                             "statement_id": sid, "evidence": evidence})
    out["transactions"] = transactions
    if any(t["group"] == "unknown" for t in transactions):
        out["warnings"].append("unknown_transactions")

    def line(key: str, amount: Decimal, *, subtotal: bool = False, proof: str | None = None):
        out["lines"].append({"key": key, "amount": None if proof == "unavailable" else amount, "share": None if proof == "unavailable" else share(amount, base),
                             "subtotal": subtotal, "evidence": proof or evidence})

    line("sale_proceeds", v["sale_proceeds"])
    line("seller_discounts", -v["seller_discounts"])
    line("revenue_base", base, subtotal=True)
    for key in ("refunds", *FEES):
        proof = "unavailable" if source == "ratio_estimate" and (key != "platform_fees" or snap.get("fee_ratio") is None) else evidence
        line(key, -v[key], proof=proof)
    line("subsidies", v["subsidies"], proof="unavailable" if source == "ratio_estimate" else evidence)
    line("adjustments", v["adjustments"], proof="unavailable" if source == "ratio_estimate" else evidence)
    line("net_seller_revenue", v["net_seller_revenue"], subtotal=True,
         proof="unavailable" if "fees" in out["unconfirmed_fields"] or snap.get("mismatch") else evidence)
    for key in COSTS:
        line(key, -v[key], proof=costs_state)
    line("contribution_profit", v["contribution_profit"], subtotal=True,
         proof="calculated" if inputs_known(p) else "unavailable")
    line("allocated_ad_cost", -v["allocated_ad_cost"], proof="estimate" if snap.get("ad_cost_known") else "unavailable")
    line("estimated_net_profit", v["estimated_net_profit"], subtotal=True,
         proof="unavailable" if "net_profit" in out["unconfirmed_fields"] else "estimate")

    expected_net = base - v["refunds"] - sum((v[k] for k in FEES), ZERO) + v["subsidies"] + v["adjustments"]
    differences = {"net_seller_revenue": expected_net - v["net_seller_revenue"],
                   "contribution_profit": v["net_seller_revenue"] - sum((v[k] for k in COSTS), ZERO) - v["contribution_profit"],
                   "estimated_net_profit": v["contribution_profit"] - v["allocated_ad_cost"] - v["estimated_net_profit"]}
    out["calculation_check"] = {"status": "matched" if not any(differences.values()) else "mismatch",
                                "differences": differences}
    ids = statement_ids(p)
    selected = [r for r in records if r.statement_id in ids]
    out["settlements"] = [{"statement_id": r.statement_id, "amount": r.settlement_amount,
                           "statement_time": r.statement_time, "fetched_at": r.fetched_at,
                           "currency": r.currency} for r in selected]
    complete = (ids and len(selected) == len(ids) and
                all(r.settlement_amount is not None and r.currency == p.currency and
                    str(r.status).upper() in ("SETTLED", "PAID") for r in selected))
    if state == "final" and complete:
        actual = sum((dec(r.settlement_amount) for r in selected), ZERO)
        difference = v["net_seller_revenue"] - actual
        out["settlement_check"] = {"status": "matched" if difference == ZERO else "mismatch",
                                   "difference": difference, "actual": actual}
    elif state == "preliminary":
        out["settlement_check"]["status"] = "pending"
    return out
