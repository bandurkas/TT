"""Pure API-dict -> model-kwargs mappers. Money = Decimal. Field names: statement transactions
verified live (fixture); orders/statements/withdrawals/analytics field names UNVERIFIED — see
docs/tiktok-api-capability-matrix.md; getters accept aliases and {amount,currency} dicts."""
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from src.db.models_finance import STATEMENT_AMOUNT_FIELDS

INTEGRATION = "tiktok_shop"


def dec(v: Any) -> Decimal | None:
    if isinstance(v, dict):
        v = v.get("amount")
    if v is None or v == "":
        return None
    if isinstance(v, float):
        v = repr(v)
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def cur(v: Any, default: str | None = None) -> str | None:
    if isinstance(v, dict):
        return v.get("currency") or default
    return default


SHOP_TZ = ZoneInfo("Asia/Jakarta")  # UNVERIFIED: analytics datetime strings assumed in shop tz


def ts(v: Any) -> datetime | None:
    if v in (None, "", 0, "0"):
        return None
    if isinstance(v, str) and not v.strip().lstrip("-").isdigit():
        d = datetime.fromisoformat(v.strip())
        return (d if d.tzinfo else d.replace(tzinfo=SHOP_TZ)).astimezone(UTC)
    n = int(v)
    if n > 10**11:  # milliseconds
        n //= 1000
    return datetime.fromtimestamp(n, UTC)


def to_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(Decimal(str(v)))
    except InvalidOperation:
        return None


def pick(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


# --- shop / catalog ------------------------------------------------------------------
def map_shop(api: dict, *, currency: str, timezone: str) -> dict:
    return {"platform": "tiktok_shop", "external_shop_id": str(api["id"]),
            "shop_cipher": api.get("cipher"), "name": api.get("name") or str(api["id"]),
            "currency": currency, "timezone": timezone, "region": api.get("region") or "",
            "status": "active"}


def map_product(api: dict, shop_id: int) -> dict:
    return {"shop_id": shop_id, "external_product_id": str(api["id"]),
            "title": api.get("title") or "", "status": api.get("status"),
            "category": _category(api)}


def _category(api: dict) -> str | None:
    chain = api.get("category_chains") or []
    if chain and isinstance(chain[-1], dict):
        return chain[-1].get("local_name") or chain[-1].get("id")
    return None


def map_sku(api: dict, product_id: int) -> dict:
    attrs = api.get("sales_attributes")
    title = ", ".join(str(a.get("value_name")) for a in attrs if a.get("value_name")) \
        if isinstance(attrs, list) else None
    return {"product_id": product_id, "external_sku_id": str(api["id"]),
            "seller_sku": api.get("seller_sku") or None, "title": title or None,
            "variation_data": {"price": api.get("price"), "sales_attributes": attrs,
                               "inventory": api.get("inventory")},
            "status": api.get("status")}


# --- orders ---------------------------------------------------------------------------
def map_order(api: dict, shop_id: int, default_currency: str) -> dict:
    p = api.get("payment") or {}
    return {"shop_id": shop_id, "external_order_id": str(api["id"]),
            "order_created_at": ts(api.get("create_time")),
            "paid_at": ts(api.get("paid_time")),
            "shipped_at": ts(pick(api, "shipping_time", "collection_time")),
            "completed_at": ts(pick(api, "delivery_time")),
            "cancelled_at": ts(pick(api, "cancel_time")),
            "order_status": api.get("status") or "UNKNOWN",
            "buyer_paid_amount": dec(p.get("total_amount")),
            "gross_merchandise_value": dec(pick(p, "original_total_product_price", "sub_total")),
            "seller_discount": dec(p.get("seller_discount")) or Decimal(0),
            "platform_discount": dec(p.get("platform_discount")) or Decimal(0),
            "shipping_amount": dec(p.get("shipping_fee")) or Decimal(0),
            "currency": p.get("currency") or default_currency,
            "raw_source_updated_at": ts(api.get("update_time"))}


def map_order_items(api: dict, order_id: int) -> list[dict]:
    """One row per line_item (TikTok emits one line per unit; quantity defaults 1).
    external_item_id is unique per order: missing or repeated ids -> "<order_id>:<idx>"."""
    out, seen = [], set()
    for idx, li in enumerate(api.get("line_items") or []):
        qty = to_int(li.get("quantity")) or 1
        sale = dec(li.get("sale_price"))
        ext = str(li.get("id") or "")
        if not ext or ext in seen:
            ext = f"{order_id}:{idx}"
        seen.add(ext)
        out.append({"order_id": order_id, "external_item_id": ext,
                    "_external_sku_id": str(li.get("sku_id") or ""),
                    "_external_product_id": str(li.get("product_id") or ""),
                    "quantity": qty, "unit_list_price": dec(li.get("original_price")),
                    "unit_sale_price": sale,
                    "gross_item_value": sale * qty if sale is not None else None,
                    "discounts": (dec(li.get("seller_discount")) or Decimal(0))
                    + (dec(li.get("platform_discount")) or Decimal(0)),
                    "attribution_source": "none"})
    return out


# --- finance --------------------------------------------------------------------------
def _amounts(rec: dict) -> dict[str, Decimal | None]:
    return {f: dec(rec.get(f)) for f in STATEMENT_AMOUNT_FIELDS}


def map_order_statement_record(rec: dict, *, shop_id: int, external_order_id: str,
                               order_create_time: Any, raw_response_id: int | None,
                               fetched_at: datetime) -> dict:
    return {"shop_id": shop_id, "external_order_id": external_order_id,
            "external_transaction_id": str(rec.get("id") or "") or None,
            "statement_id": str(rec.get("statement_id") or ""),
            "statement_time": ts(rec.get("statement_time")),
            "order_create_time": ts(order_create_time), "status": rec.get("status"),
            "currency": rec.get("currency"), "raw_response_id": raw_response_id,
            "fetched_at": fetched_at, **_amounts(rec)}


def map_order_statement_sku_records(rec: dict, record_id: int) -> list[dict]:
    return [{"record_id": record_id, "external_sku_id": str(s.get("sku_id") or ""),
             "sku_name": s.get("sku_name"), "product_name": s.get("product_name"),
             "quantity": to_int(s.get("quantity")), "currency": s.get("currency"),
             **_amounts(s)} for s in rec.get("sku_statement_transactions") or []]


def map_statement(api: dict, shop_id: int, default_currency: str) -> dict:
    revenue, fee, adj = dec(api.get("revenue_amount")), dec(api.get("fee_amount")), \
        dec(api.get("adjustment_amount"))
    net = dec(api.get("settlement_amount"))
    deductions = (fee or Decimal(0)) + (adj or Decimal(0)) if (fee is not None or adj is not None) \
        else None
    return {"shop_id": shop_id, "external_settlement_id": str(api["id"]),
            "settlement_at": ts(api.get("statement_time")),
            "gross_amount": revenue, "deductions": deductions, "net_amount": net,
            "currency": api.get("currency") or default_currency,
            "status": api.get("payment_status") or api.get("status"),
            "extra": {k: v for k, v in api.items() if k != "id"}}


def map_withdrawal(api: dict, shop_id: int, default_currency: str) -> dict:
    return {"shop_id": shop_id, "external_payout_id": str(api["id"]),
            "payout_amount": dec(api.get("amount")) or Decimal(0),
            "currency": cur(api.get("amount")) or api.get("currency") or default_currency,
            "payout_status": api.get("status"), "initiated_at": ts(api.get("create_time")),
            "payout_type": api.get("type")}


# --- analytics (202509) ---------------------------------------------------------------
def map_video(api: dict, shop_id: int) -> dict:
    return {"shop_id": shop_id, "external_video_id": str(api["id"]),
            "account_type": "unknown", "published_at": ts(api.get("video_post_time")),
            "duration_seconds": to_int(api.get("duration")), "caption": api.get("title"),
            "video_reference": api.get("username")}


def map_video_metric(api: dict, video_id: int, day: date, fetched_at: datetime) -> dict:
    return {"video_id": video_id, "metric_date": day, "metric_hour": None,
            "views": to_int(api.get("views")) or 0,
            "impressions": to_int(pick(api, "product_impressions", "impressions")),
            "product_clicks": to_int(pick(api, "product_clicks", "clicks")) or 0,
            "ctr": dec(pick(api, "ctr", "click_through_rate")),
            "orders": to_int(pick(api, "sku_orders", "orders")) or 0,
            "units_sold": to_int(pick(api, "items_sold", "units_sold")) or 0,
            "gmv": dec(api.get("gmv")) or Decimal(0), "gpm": dec(api.get("gpm")),
            "conversion_rate": dec(pick(api, "conversion_rate")),
            "likes": to_int(api.get("likes")), "comments": to_int(api.get("comments")),
            "shares": to_int(api.get("shares")), "fetched_at": fetched_at, "is_final": False}


def _metric_common(api: dict) -> dict:
    return {"views": to_int(pick(api, "product_impressions", "impressions", "views")) or 0,
            "clicks": to_int(pick(api, "product_clicks", "clicks")) or 0,
            "orders": to_int(pick(api, "sku_orders", "orders")) or 0,
            "units": to_int(pick(api, "items_sold", "units_sold", "units")) or 0,
            "gmv": dec(api.get("gmv")) or Decimal(0),
            "refunds": dec(pick(api, "refunds", "refund_amount")) or Decimal(0)}


def map_product_metric(api: dict, product_id: int, day: date, fetched_at: datetime) -> dict:
    return {"product_id": product_id, "sku_id": None, "metric_date": day,
            "fetched_at": fetched_at, **_metric_common(api)}


def map_sku_metric(api: dict, product_id: int, sku_id: int, day: date,
                   fetched_at: datetime) -> dict:
    return {"product_id": product_id, "sku_id": sku_id, "metric_date": day,
            "fetched_at": fetched_at, **_metric_common(api)}


def _breakdown(items: Any) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for b in items or []:
        if isinstance(b, dict) and b.get("type"):
            amt = dec(pick(b, "amount", "gmv", "gross_revenue"))
            if amt is not None:
                out[str(b["type"]).upper()] = amt
    return out


def map_shop_metric(api: dict, shop_id: int, day: date, fetched_at: datetime) -> dict:
    """Shape verified live 2026-08-30: performance.intervals[0].sales{gmv{overall,breakdowns[{gmv,type}]},
    gross_revenue{overall,breakdowns[{type,percentage}]}, refunds, items_sold, orders_count,
    sku_orders_count, avg_customers_count}, traffic{avg_visitors, avg_page_views, avg_conversation_rate}."""
    perf = api.get("performance", api)
    ivs = perf.get("intervals") if isinstance(perf, dict) else None
    iv = ivs[0] if isinstance(ivs, list) and ivs else perf
    sales = iv.get("sales", iv)
    gmv = sales.get("gmv") or {}
    gmv_b = {b.get("type"): dec((b.get("gmv") or {}).get("amount")) for b in gmv.get("breakdowns") or []}
    gr = sales.get("gross_revenue") or {}
    gr_total = dec((gr.get("overall") or {}).get("amount"))
    pcts = {b.get("type"): dec(b.get("percentage")) for b in gr.get("breakdowns") or []}
    pct = pcts.get("GMV_MAX")
    gmv_max = (gr_total * pct) if gr_total is not None and pct is not None else None
    non = (gr_total - gmv_max) if gmv_max is not None else None
    return {"shop_id": shop_id, "metric_date": day,
            "gmv_total": dec((gmv.get("overall") or {}).get("amount")),
            "gmv_live": gmv_b.get("LIVE"), "gmv_video": gmv_b.get("VIDEO"),
            "gmv_product_card": gmv_b.get("PRODUCT_CARD"),
            "gross_revenue_gmv_max": gmv_max, "gross_revenue_non_gmv_max": non,
            "gross_revenue_gmv_max_pct": pct,
            "sku_orders": to_int(sales.get("sku_orders_count")),
            "avg_customers": dec(sales.get("avg_customers_count")),
            "currency": cur(gmv.get("overall"), "IDR"), "breakdown": api, "fetched_at": fetched_at}
