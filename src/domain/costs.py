"""Product cost lots -> date-effective sku_cost_versions.

A lot (CostBatch) says: from `received_on` this SKU (or product, or every SKU) costs `unit_cost`;
with `quantity` the lot is consumed FIFO by sold units and the next lot takes over the day after it
runs out; without quantity it applies until the next lot's date. Versions are regenerated
deterministically (notes `lot:<id>`); manual/seed versions of a SKU are kept only while it has no lots.
Money = Decimal; the profit engine keeps picking versions by order date, so this stays auditable."""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from src.db.models import Order, OrderItem, Product, Sku, SkuCostVersion
from src.db.models_costs import CostBatch
from src.domain.profit.jobs import DEFAULT_TZ, SKIP_ORDER_STATUSES, local_date

log = logging.getLogger("tt.costs")
LOT_NOTE = "lot:"


@dataclass(frozen=True)
class Lot:
    id: int
    received_on: date
    unit_cost: Decimal
    quantity: int | None


@dataclass(frozen=True)
class Segment:
    effective_from: date
    effective_to: date | None
    unit_cost: Decimal
    lot_id: int
    consumed: int
    remaining: int | None


def segments_for_sku(lots: Sequence[Lot], sold: Iterable[tuple[date, int]]) -> list[Segment]:
    """Pure FIFO: a lot with quantity is sold out before the next lot starts (the day it runs out is still
    charged at its cost; the next lot starts the day after, or on its received_on if later). A lot without
    quantity ends when the next lot arrives. While a quantified lot is still in stock, later lots are
    queued (not yet applied)."""
    lots = sorted(lots, key=lambda x: (x.received_on, x.id))
    if not lots:
        return []
    by_day: dict[date, int] = defaultdict(int)
    for d, q in sold:
        by_day[d] += q
    days = sorted(by_day)
    out: list[Segment] = []
    start = lots[0].received_on
    for i, lot in enumerate(lots):
        nxt = lots[i + 1] if i + 1 < len(lots) else None
        consumed = 0
        exhausted_on: date | None = None
        if lot.quantity is not None:  # pure FIFO: sell this lot out before the next one starts
            for d in days:
                if d < start:
                    continue
                consumed += by_day[d]
                if consumed >= lot.quantity:
                    exhausted_on = d
                    break
        if nxt is None:
            end = None
        elif lot.quantity is None:
            end = nxt.received_on
        elif exhausted_on is not None:
            end = max(exhausted_on + timedelta(days=1), nxt.received_on)
        else:
            end = None  # still in stock: later lots are queued until this one runs out
        remaining = None if lot.quantity is None else max(lot.quantity - consumed, 0)
        out.append(Segment(start, end, lot.unit_cost, lot.id, consumed, remaining))
        if end is None:
            break
        start = end
    return out


def _sold_by_sku(session: Any, shop_id: int, tz: str) -> dict[int, list[tuple[date, int]]]:
    q = (select(OrderItem.sku_id, OrderItem.quantity, Order.order_created_at, Order.order_status)
         .join(Order, Order.id == OrderItem.order_id).where(Order.shop_id == shop_id))
    out: dict[int, list[tuple[date, int]]] = defaultdict(list)
    for sku_id, qty, created, status in session.execute(q):
        if sku_id is None or str(status or "").upper() in SKIP_ORDER_STATUSES:
            continue
        d = local_date(created, tz)
        if d is not None:
            out[sku_id].append((d, int(qty or 0)))
    return out


def lots_for_sku(batches: Sequence[Any], sku: Any) -> list[Lot]:
    """Most specific scope wins: sku > product > all (scopes are not mixed)."""
    for scope, pred in (("sku", lambda b: b.sku_id == sku.id), ("product", lambda b: b.product_id == sku.product_id),
                        ("all", lambda b: True)):
        chosen = [b for b in batches if b.active and b.scope == scope and pred(b)]
        if chosen:
            return [Lot(b.id, b.received_on, Decimal(str(b.unit_cost)), b.quantity) for b in chosen]
    return []


def rebuild_cost_versions(session: Any, shop_id: int, currency: str, tz: str | None = None) -> dict[str, Any]:
    """Regenerate lot-derived sku_cost_versions for every SKU of the shop. Commits.

    SKUs sharing the same physical batch (a scope="all"/"product" lot with no more specific override)
    are grouped by their resolved lot list (same lot ids -> same purchase) so `quantity` is consumed
    once against their COMBINED sales, not once per SKU. Any pre-existing seed/manual cost version for
    a SKU that would overlap its first lot segment is clamped (`effective_to` = the lot's start date)
    instead of being deleted or left to collide -- so version selection stays deterministic and the
    seed price still covers the period genuinely before the earliest lot.
    """
    tz = tz or DEFAULT_TZ
    batches = list(session.scalars(select(CostBatch).where(CostBatch.shop_id == shop_id)))
    skus = list(session.scalars(select(Sku).join(Product, Product.id == Sku.product_id)
                                .where(Product.shop_id == shop_id)))
    existing = list(session.scalars(select(SkuCostVersion).where(SkuCostVersion.sku_id.in_([s.id for s in skus]))))
    lot_versions = [v for v in existing if (v.notes or "").startswith(LOT_NOTE)]
    other_by_sku: dict[int, list[Any]] = defaultdict(list)
    for v in existing:
        if v not in lot_versions:
            other_by_sku[v.sku_id].append(v)
    for v in lot_versions:
        session.delete(v)
    session.flush()
    if not any(b.active for b in batches):
        session.commit()
        return {"skus_with_lots": 0, "versions": 0, "segments": {}}
    sold = _sold_by_sku(session, shop_id, tz)

    groups: dict[tuple[int, ...], list[Any]] = defaultdict(list)
    sku_lots: dict[tuple[int, ...], list[Lot]] = {}
    for sku in skus:
        lots = lots_for_sku(batches, sku)
        if not lots:
            continue
        key = tuple(x.id for x in lots)
        groups[key].append(sku)
        sku_lots[key] = lots

    per_sku: dict[int, list[Segment]] = {}
    n = 0
    for key, group_skus in groups.items():
        merged_sold: list[tuple[date, int]] = []
        for sku in group_skus:
            merged_sold.extend(sold.get(sku.id, []))
        segs = segments_for_sku(sku_lots[key], merged_sold)
        if not segs:
            continue
        lot_start = segs[0].effective_from
        shared = "|".join(str(x) for x in key) if len(group_skus) > 1 else None
        for sku in group_skus:
            for v in other_by_sku.get(sku.id, ()):
                if v.effective_from < lot_start and (v.effective_to is None or v.effective_to > lot_start):
                    v.effective_to = lot_start  # seed/manual price still covers time before the first lot
                elif v.effective_from >= lot_start and (v.effective_to is None or v.effective_to > v.effective_from):
                    v.effective_to = v.effective_from  # fully superseded -> zero-length, never selected
            per_sku[sku.id] = segs
            for s in segs:
                note = f"{LOT_NOTE}{s.lot_id} consumed={s.consumed} remaining={s.remaining}"
                if shared:
                    note += f" shared_batch={shared} shared_skus={len(group_skus)}"
                session.add(SkuCostVersion(sku_id=sku.id, effective_from=s.effective_from,
                                           effective_to=s.effective_to, cogs_per_unit=s.unit_cost,
                                           currency=currency, notes=note))
                n += 1
    session.commit()
    log.info("cost versions rebuilt: shop=%s skus_with_lots=%d versions=%d", shop_id, len(per_sku), n)
    return {"skus_with_lots": len(per_sku), "versions": n, "segments": per_sku}


def cost_overview(session: Any, shop_id: int, cfg: Any, today: date, tz: str | None = None) -> dict[str, Any]:
    """Current cost per SKU + where it comes from (lot / seed version / shop default / none)."""
    tz = tz or DEFAULT_TZ
    batches = list(session.scalars(select(CostBatch).where(CostBatch.shop_id == shop_id)
                                   .order_by(CostBatch.received_on, CostBatch.id)))
    rows = list(session.execute(select(Sku, Product).join(Product, Product.id == Sku.product_id)
                                .where(Product.shop_id == shop_id).order_by(Product.id, Sku.id)))
    versions = list(session.scalars(select(SkuCostVersion).where(SkuCostVersion.sku_id.in_([s.id for s, _ in rows]))))
    by_sku: dict[int, list[Any]] = defaultdict(list)
    for v in versions:
        by_sku[v.sku_id].append(v)
    default = Decimal(str(cfg.default_cogs_per_unit)) if cfg is not None and cfg.default_cogs_per_unit is not None else None
    skus = []
    for sku, prod in rows:
        cur = [v for v in by_sku[sku.id] if v.effective_from <= today and (v.effective_to is None or today < v.effective_to)]
        v = max(cur, key=lambda x: x.effective_from) if cur else None
        src = "none"
        lot_id = None
        if v is not None:
            src = "lot" if (v.notes or "").startswith(LOT_NOTE) else "seed"
            if src == "lot":
                lot_id = int((v.notes or "")[len(LOT_NOTE):].split()[0])
        elif default is not None:
            src = "default"
        skus.append({"sku_id": sku.id, "external_sku_id": sku.external_sku_id, "product_id": prod.id,
                     "product_title": prod.title, "sku_title": sku.title,
                     "current_cost": Decimal(str(v.cogs_per_unit)) if v is not None else default,
                     "source": src, "lot_id": lot_id, "effective_from": v.effective_from if v else None,
                     "history": [{"effective_from": x.effective_from, "effective_to": x.effective_to,
                                  "cogs_per_unit": Decimal(str(x.cogs_per_unit)), "notes": x.notes}
                                 for x in sorted(by_sku[sku.id], key=lambda x: x.effective_from)]})
    lots = [{"id": b.id, "scope": b.scope, "product_id": b.product_id, "sku_id": b.sku_id,
             "received_on": b.received_on, "unit_cost": Decimal(str(b.unit_cost)), "quantity": b.quantity,
             "currency": b.currency, "note": b.note, "active": b.active} for b in batches]
    # consumption per lot from the generated versions' notes (identical across every SKU sharing the batch)
    for lot in lots:
        cons = [v for v in versions if (v.notes or "").startswith(f"{LOT_NOTE}{lot['id']} ")]
        if cons:
            parts = dict(tok.split("=", 1) for tok in cons[0].notes.split()[1:])
            lot["consumed"] = int(parts.get("consumed", 0))
            lot["remaining"] = None if parts.get("remaining") == "None" else int(parts.get("remaining", 0))
            lot["shared_skus"] = int(parts["shared_skus"]) if "shared_skus" in parts else None
    return {"default_cogs_per_unit": default, "lots": lots, "skus": skus,
            "note": "A scope=all/product lot's quantity is one shared purchase batch: consumed FIFO against "
                    "the COMBINED sales of every SKU it covers, not per SKU (see lot.shared_skus). "
                    "scope=sku lots track that one SKU alone. A lot without quantity applies until the next "
                    "one; the day a lot runs out is still charged at its cost. A SKU's own seed/manual cost "
                    "still covers the time genuinely before its first lot. Versions are regenerated on every "
                    "change and past orders are recomputed."}
