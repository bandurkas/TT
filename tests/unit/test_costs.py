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


# --- rebuild_cost_versions: shared batches + seed clamping (in-memory fake session) ---------------
class FakeSession:
    def __init__(self, batches, skus, versions, order_rows):
        self._batches, self._skus, self._versions, self._order_rows = batches, skus, list(versions), order_rows
        self.deleted: list = []
        self.added: list = []
        self.committed = False

    def scalars(self, stmt):
        text = str(stmt)
        if "cost_batches" in text:
            return list(self._batches)
        if "sku_cost_versions" in text:
            return list(self._versions)
        if "skus" in text and "products" in text:
            return list(self._skus)
        raise AssertionError("unexpected scalars() call: " + text[:120])

    def execute(self, stmt):
        return list(self._order_rows)

    def delete(self, obj):
        self.deleted.append(obj)
        self._versions.remove(obj)

    def flush(self):
        pass

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


def _sku(id_, product_id, ext=None, title=None):
    return NS(id=id_, product_id=product_id, external_sku_id=ext or f"sku{id_}", title=title)


def _batch(id_, scope, received_on, unit_cost, quantity, product_id=None, sku_id=None, active=True):
    return NS(id=id_, shop_id=1, scope=scope, product_id=product_id, sku_id=sku_id, received_on=received_on,
              unit_cost=unit_cost, quantity=quantity, currency="IDR", note=None, active=active)


def _order_row(sku_id, qty, day, status="COMPLETED"):
    return (sku_id, qty, NS(astimezone=lambda tz: NS(date=lambda: day)), status)


def test_rebuild_shares_quantity_across_skus_of_one_batch(monkeypatch):
    from src.domain import costs as C
    skus = [_sku(1, 100), _sku(2, 100)]  # same product, both fall under one scope="all" batch
    batch = _batch(1, "all", d(2026, 9, 1), D(20000), 5)
    rows = [_order_row(1, 3, d(2026, 9, 2)), _order_row(2, 3, d(2026, 9, 3))]  # 6 units total, sku1+sku2
    session = FakeSession([batch], skus, [], rows)
    monkeypatch.setattr(C, "local_date", lambda ts, tz: ts.astimezone(tz).date())
    out = C.rebuild_cost_versions(session, shop_id=1, currency="IDR", tz="Asia/Jakarta")
    assert out["skus_with_lots"] == 2 and session.committed is True
    versions = [v for v in session.added if hasattr(v, "sku_id")]
    v1 = [v for v in versions if v.sku_id == 1]
    v2 = [v for v in versions if v.sku_id == 2]
    # both SKUs see the SAME segment boundaries because the batch is shared: lot exhausted at day 2 (6 >= 5 qty)
    assert len(v1) == 1 and len(v2) == 1
    assert v1[0].effective_from == v2[0].effective_from == d(2026, 9, 1)
    assert "shared_batch=1" in v1[0].notes and "shared_skus=2" in v1[0].notes
    assert "consumed=6" in v1[0].notes and "remaining=0" in v1[0].notes  # combined consumption, not 3 each


def test_rebuild_sku_scope_batch_is_not_shared(monkeypatch):
    from src.domain import costs as C
    skus = [_sku(1, 100), _sku(2, 100)]
    b1 = _batch(1, "sku", d(2026, 9, 1), D(20000), None, sku_id=1)
    b2 = _batch(2, "sku", d(2026, 9, 1), D(18000), None, sku_id=2)
    session = FakeSession([b1, b2], skus, [], [])
    monkeypatch.setattr(C, "local_date", lambda ts, tz: ts.astimezone(tz).date())
    out = C.rebuild_cost_versions(session, shop_id=1, currency="IDR", tz="Asia/Jakarta")
    assert out["skus_with_lots"] == 2
    versions = [v for v in session.added if hasattr(v, "sku_id")]
    assert {v.sku_id: v.cogs_per_unit for v in versions} == {1: D(20000), 2: D(18000)}
    assert all("shared_batch" not in v.notes for v in versions)


def test_rebuild_clamps_seed_version_around_lot_and_zeroes_later_seed(monkeypatch):
    from src.domain import costs as C
    skus = [_sku(1, 100)]
    seed_before = NS(id=901, sku_id=1, effective_from=d(2026, 1, 1), effective_to=None, cogs_per_unit=D(25000),
                     currency="IDR", notes=None)
    batch = _batch(1, "sku", d(2026, 8, 20), D(20000), None, sku_id=1)
    session = FakeSession([batch], skus, [seed_before], [])
    monkeypatch.setattr(C, "local_date", lambda ts, tz: ts.astimezone(tz).date())
    C.rebuild_cost_versions(session, shop_id=1, currency="IDR", tz="Asia/Jakarta")
    assert seed_before.effective_to == d(2026, 8, 20)  # seed still covers Jan-Aug, lot takes over after

    seed_after = NS(id=902, sku_id=1, effective_from=d(2026, 9, 1), effective_to=None, cogs_per_unit=D(30000),
                    currency="IDR", notes=None)
    session2 = FakeSession([batch], skus, [seed_after], [])
    C.rebuild_cost_versions(session2, shop_id=1, currency="IDR", tz="Asia/Jakarta")
    assert seed_after.effective_to == seed_after.effective_from  # zero-length: fully superseded, never selected


def test_rebuild_no_active_batches_is_a_cheap_noop(monkeypatch):
    from src.domain import costs as C
    called = []
    monkeypatch.setattr(C, "_sold_by_sku", lambda *a, **k: called.append(1) or {})
    session = FakeSession([_batch(1, "all", d(2026, 1, 1), D(1), None, active=False)], [_sku(1, 100)], [], [])
    out = C.rebuild_cost_versions(session, shop_id=1, currency="IDR", tz="Asia/Jakarta")
    assert out == {"skus_with_lots": 0, "versions": 0, "segments": {}}
    assert not called and session.committed is True


def test_cost_overview_reports_shared_lot_once(monkeypatch):
    from src.domain import costs as C
    batch = _batch(1, "all", d(2026, 9, 1), D(20000), 5)
    v1 = NS(sku_id=1, effective_from=d(2026, 9, 1), effective_to=None, cogs_per_unit=D(20000), currency="IDR",
           notes="lot:1 consumed=6 remaining=0 shared_batch=1 shared_skus=2")
    v2 = NS(sku_id=2, effective_from=d(2026, 9, 1), effective_to=None, cogs_per_unit=D(20000), currency="IDR",
           notes="lot:1 consumed=6 remaining=0 shared_batch=1 shared_skus=2")
    prod = NS(id=100, title="Socks")
    session = MockSession(rows=[(_sku(1, 100, title="A"), prod), (_sku(2, 100, title="A"), prod)], versions=[v1, v2], batches=[batch])
    out = C.cost_overview(session, shop_id=1, cfg=None, today=d(2026, 9, 5), tz="Asia/Jakarta")
    assert out["lots"][0]["consumed"] == 6 and out["lots"][0]["remaining"] == 0 and out["lots"][0]["shared_skus"] == 2
    assert {s["sku_id"]: s["current_cost"] for s in out["skus"]} == {1: D(20000), 2: D(20000)}


class MockSession:
    def __init__(self, rows, versions, batches):
        self.rows, self.versions, self.batches = rows, versions, batches

    def scalars(self, stmt):
        text = str(stmt)
        if "cost_batches" in text:
            return list(self.batches)
        if "sku_cost_versions" in text:
            return list(self.versions)
        raise AssertionError(text[:120])

    def execute(self, stmt):
        return list(self.rows)
