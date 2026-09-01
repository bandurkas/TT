from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace as NS

from src.domain import costs as C

d = date


def test_segments_fifo_with_quantities():
    lots = [C.Lot(1, d(2026, 1, 1), D(25000), 10), C.Lot(2, d(2026, 8, 20), D(20000), 5), C.Lot(3, d(2026, 9, 10), D(18000), None)]
    sold = [(d(2026, 8, 18), 4), (d(2026, 8, 21), 3), (d(2026, 8, 22), 5), (d(2026, 8, 25), 2), (d(2026, 9, 12), 1)]
    segs = C.segments_for_sku(lots, sold)
    # lot 1: 10 units; sales 18 Aug (4) + 21 Aug (3) + 22 Aug (5) -> exhausted on 22 Aug -> ends 23 Aug
    assert (segs[0].effective_from, segs[0].effective_to, segs[0].unit_cost) == (d(2026, 1, 1), d(2026, 8, 23), D(25000))
    assert segs[0].consumed == 12 and segs[0].remaining == 0
    # lot 2 from 23 Aug: 25 Aug (2) + 12 Sep (1) = 3 of 5 -> still in stock, so lot 3 stays queued
    assert (segs[1].effective_from, segs[1].effective_to) == (d(2026, 8, 23), None)
    assert segs[1].consumed == 3 and segs[1].remaining == 2 and len(segs) == 2
    more = C.segments_for_sku(lots, sold + [(d(2026, 9, 20), 2)])  # lot 2 exhausted 20 Sep -> lot 3 from 21 Sep
    assert (more[1].effective_to, more[2].effective_from, more[2].effective_to) == (d(2026, 9, 21), d(2026, 9, 21), None)
    assert more[2].unit_cost == D(18000) and more[2].remaining is None


def test_segments_never_end_before_next_lot_and_open_ended_last():
    lots = [C.Lot(1, d(2026, 1, 1), D(25000), 2), C.Lot(2, d(2026, 9, 1), D(20000), 1)]
    segs = C.segments_for_sku(lots, [(d(2026, 3, 1), 5), (d(2026, 9, 5), 9)])
    assert segs[0].effective_to == d(2026, 9, 1)  # exhausted in March but nothing else to sell until Sep 1
    assert segs[1].effective_to is None and segs[1].consumed == 9 and segs[1].remaining == 0
    assert C.segments_for_sku([], []) == []
    single = C.segments_for_sku([C.Lot(7, d(2026, 1, 1), D(25000), None)], [])
    assert single == [C.Segment(d(2026, 1, 1), None, D(25000), 7, 0, None)]


def test_lots_for_sku_scope_precedence():
    sku = NS(id=5, product_id=3)
    batches = [NS(id=1, active=True, scope="all", product_id=None, sku_id=None, received_on=d(2026, 1, 1), unit_cost=25000, quantity=None),
               NS(id=2, active=True, scope="product", product_id=3, sku_id=None, received_on=d(2026, 8, 1), unit_cost=22000, quantity=None),
               NS(id=3, active=False, scope="sku", product_id=None, sku_id=5, received_on=d(2026, 8, 1), unit_cost=1, quantity=None)]
    assert [x.id for x in C.lots_for_sku(batches, sku)] == [2]  # product beats all; inactive sku lot ignored
    assert [x.id for x in C.lots_for_sku(batches, NS(id=9, product_id=4))] == [1]
    assert C.lots_for_sku([], sku) == []
