from decimal import Decimal

from src.analytics.reconciliation import (
    FinanceTxn,
    Order,
    OrderItem,
    Payout,
    ReconStatus,
    Settlement,
    reconcile,
)

D = Decimal


def test_statuses_per_order():
    orders = [Order("m", D(100)), Order("p", D(100)), Order("x", D(100)), Order("pend", D(50)),
              Order("items_bad", D(100))]
    items = [OrderItem("m", D(60)), OrderItem("m", D(40)), OrderItem("p", D(100)),
             OrderItem("x", D(100)), OrderItem("pend", D(50)), OrderItem("items_bad", D(90))]
    txns = [FinanceTxn("t1", "m", D(85)), FinanceTxn("t2", "p", D(85)),
            FinanceTxn("t3", "x", D(85)), FinanceTxn("t4", "items_bad", D(85))]
    setts = [Settlement("s1", "m", D(85)), Settlement("s2", "p", D(40), is_final=False),
             Settlement("s3", "x", D(80)), Settlement("s4", "items_bad", D(85))]
    r = reconcile(orders, items, txns, setts, [Payout("po", D(250))])
    by = {o.order_id: o for o in r.orders}
    assert by["m"].status == ReconStatus.MATCHED and by["m"].difference == D(0)
    assert by["p"].status == ReconStatus.PARTIAL and by["p"].difference == D(-45)
    assert by["x"].status == ReconStatus.MISMATCH and by["x"].difference == D(-5)
    assert by["pend"].status == ReconStatus.PENDING and by["pend"].settlement_total is None
    assert by["items_bad"].status == ReconStatus.MISMATCH
    assert any("items 90 != order total 100" in n for n in by["items_bad"].notes)
    assert r.counts[ReconStatus.MATCHED] == 1 and r.counts[ReconStatus.MISMATCH] == 2
    assert r.counts[ReconStatus.PARTIAL] == 1 and r.counts[ReconStatus.PENDING] == 1
    assert r.total_difference == D(-50)
    assert r.settlements_total == D(250) and r.payout_difference == D(0)


def test_tolerance_and_orphans():
    r = reconcile([Order("a", D(100))], [OrderItem("a", D(100))],
                  [FinanceTxn("t", "a", D("85.00")), FinanceTxn("t2", "ghost", D(1))],
                  [Settlement("s", "a", D("84.99")), Settlement("s2", "ghost", D(1))],
                  tolerance=D("0.05"))
    assert r.orders[0].status == ReconStatus.MATCHED
    assert r.orders[0].difference == D("-0.01")
    assert r.orphan_txns == 1 and r.orphan_settlements == 1
    assert len(r.notes) == 2


def test_settlement_without_txns_compares_to_order_total():
    r = reconcile([Order("a", D(100))], [OrderItem("a", D(100))], [],
                  [Settlement("s", "a", D(90))])
    assert r.orders[0].status == ReconStatus.MISMATCH
    assert r.orders[0].difference == D(-10)
    assert any("order total" in n for n in r.orders[0].notes)


def test_payout_shortfall_noted():
    r = reconcile([Order("a", D(100))], [OrderItem("a", D(100))], [FinanceTxn("t", "a", D(90))],
                  [Settlement("s", "a", D(90))], [Payout("p", D(70))])
    assert r.payout_difference == D(-20)
    assert any("payouts 70 vs final settlements 90" in n for n in r.notes)
