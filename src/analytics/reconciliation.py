"""Orders -> items -> finance txns -> settlements -> payouts reconciliation (SPEC §19)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal(0)


class ReconStatus(StrEnum):
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    MISMATCH = "MISMATCH"
    PENDING = "PENDING"


@dataclass(frozen=True)
class Order:
    order_id: str
    total: Decimal


@dataclass(frozen=True)
class OrderItem:
    order_id: str
    amount: Decimal


@dataclass(frozen=True)
class FinanceTxn:
    txn_id: str
    order_id: str
    amount: Decimal


@dataclass(frozen=True)
class Settlement:
    settlement_id: str
    order_id: str
    amount: Decimal
    is_final: bool = True


@dataclass(frozen=True)
class Payout:
    payout_id: str
    amount: Decimal


@dataclass(frozen=True)
class OrderReconciliation:
    order_id: str
    status: ReconStatus
    order_total: Decimal
    items_total: Decimal
    txn_total: Decimal | None
    settlement_total: Decimal | None
    difference: Decimal
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationSummary:
    orders: tuple[OrderReconciliation, ...]
    counts: dict[ReconStatus, int]
    total_difference: Decimal
    settlements_total: Decimal
    payouts_total: Decimal
    payout_difference: Decimal
    orphan_txns: int = 0
    orphan_settlements: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


def _reconcile_order(
    o: Order,
    items: Sequence[OrderItem],
    txns: Sequence[FinanceTxn],
    setts: Sequence[Settlement],
    tol: Decimal,
) -> OrderReconciliation:
    notes: list[str] = []
    items_total = sum((i.amount for i in items), ZERO)
    txn_total = sum((t.amount for t in txns), ZERO) if txns else None
    sett_total = sum((s.amount for s in setts), ZERO) if setts else None
    items_diff = items_total - o.total
    item_mismatch = bool(items) and abs(items_diff) > tol
    if item_mismatch:
        notes.append(f"items {items_total} != order total {o.total} (diff {items_diff})")
    if not items:
        notes.append("no order items")

    if sett_total is None:
        diff = items_diff if item_mismatch else ZERO
        if txn_total is not None:
            notes.append(f"finance txns {txn_total} recorded, no settlement yet")
        status = ReconStatus.MISMATCH if item_mismatch else ReconStatus.PENDING
        return OrderReconciliation(o.order_id, status, o.total, items_total, txn_total,
                                   sett_total, diff, tuple(notes))

    expected = txn_total if txn_total is not None else o.total
    basis = "finance txns" if txn_total is not None else "order total"
    diff = sett_total - expected
    final = all(s.is_final for s in setts)
    if abs(diff) > tol:
        notes.append(f"settlement {sett_total} vs {basis} {expected} (diff {diff})")
    if item_mismatch:
        status = ReconStatus.MISMATCH
    elif not final:
        notes.append("settlement provisional")
        status = ReconStatus.PARTIAL
    elif abs(diff) > tol:
        status = ReconStatus.MISMATCH
    else:
        status = ReconStatus.MATCHED
    return OrderReconciliation(o.order_id, status, o.total, items_total, txn_total, sett_total,
                               diff, tuple(notes))


def reconcile(
    orders: Sequence[Order],
    items: Sequence[OrderItem],
    txns: Sequence[FinanceTxn],
    settlements: Sequence[Settlement],
    payouts: Sequence[Payout] = (),
    tolerance: Decimal = ZERO,
) -> ReconciliationSummary:
    items_by: dict[str, list[OrderItem]] = defaultdict(list)
    txns_by: dict[str, list[FinanceTxn]] = defaultdict(list)
    setts_by: dict[str, list[Settlement]] = defaultdict(list)
    for i in items:
        items_by[i.order_id].append(i)
    for t in txns:
        txns_by[t.order_id].append(t)
    for s in settlements:
        setts_by[s.order_id].append(s)
    known = {o.order_id for o in orders}
    orphan_txns = sum(1 for t in txns if t.order_id not in known)
    orphan_setts = sum(1 for s in settlements if s.order_id not in known)

    results = tuple(
        _reconcile_order(o, items_by.get(o.order_id, ()), txns_by.get(o.order_id, ()),
                         setts_by.get(o.order_id, ()), tolerance)
        for o in orders
    )
    counts = {s: 0 for s in ReconStatus}
    for r in results:
        counts[r.status] += 1
    final_setts = sum((s.amount for s in settlements if s.is_final), ZERO)
    payouts_total = sum((p.amount for p in payouts), ZERO)
    notes: list[str] = []
    if orphan_txns:
        notes.append(f"{orphan_txns} finance txns reference unknown orders")
    if orphan_setts:
        notes.append(f"{orphan_setts} settlements reference unknown orders")
    payout_diff = payouts_total - final_setts
    if payouts and abs(payout_diff) > tolerance:
        notes.append(f"payouts {payouts_total} vs final settlements {final_setts} "
                     f"(diff {payout_diff})")
    return ReconciliationSummary(
        orders=results,
        counts=counts,
        total_difference=sum((r.difference for r in results), ZERO),
        settlements_total=final_setts,
        payouts_total=payouts_total,
        payout_difference=payout_diff,
        orphan_txns=orphan_txns,
        orphan_settlements=orphan_setts,
        notes=tuple(notes),
    )
