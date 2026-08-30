from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.ingest.cogs import parse_cogs_csv
from src.domain.ingest.state import days_to_sync, next_cursor, time_window

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def test_time_window_without_cursor_uses_default_days():
    ge, lt = time_window(None, now=NOW, default_days=60)
    assert lt == int(NOW.timestamp()) and ge == int((NOW - timedelta(days=60)).timestamp())


def test_time_window_with_cursor_overlaps():
    c = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
    ge, _ = time_window(c.isoformat(), now=NOW, default_days=60)
    assert ge == int((c - timedelta(hours=1)).timestamp())
    ge2, _ = time_window(c.isoformat(), now=NOW, default_days=60, overlap=timedelta(days=7))
    assert ge2 == int((c - timedelta(days=7)).timestamp())


def test_next_cursor_monotonic():
    a, b = datetime(2026, 8, 20, tzinfo=UTC), datetime(2026, 8, 25, tzinfo=UTC)
    assert next_cursor(None, [a, None, b]) == "2026-08-25T00:00:00+00:00"
    assert next_cursor("2026-08-28T00:00:00+00:00", [a, b]) == "2026-08-28T00:00:00+00:00"
    assert next_cursor(None, [None]) is None and next_cursor("2026-08-01T00:00:00+00:00", []) == "2026-08-01T00:00:00+00:00"


def test_days_to_sync():
    today = date(2026, 8, 30)
    d = days_to_sync(None, today_local=today, default_days=5)
    assert d == [date(2026, 8, 25) + timedelta(days=i) for i in range(5)]
    assert d[-1] == date(2026, 8, 29)  # D-1
    d2 = days_to_sync("2026-08-29", today_local=today, default_days=60)
    assert d2 == [date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 29)]
    assert days_to_sync("2026-08-29", today_local=today, default_days=60, resync_days=1) == [date(2026, 8, 29)]
    assert days_to_sync("2026-09-05", today_local=today, default_days=60, resync_days=1) == []


def test_parse_cogs_seed():
    rows = parse_cogs_csv(Path(__file__).parents[2] / "seed" / "cogs_seed.csv")
    assert len(rows) == 45
    assert {r.cogs_per_unit for r in rows} == {Decimal(25000), Decimal(50000)}
    kids = [r for r in rows if r.pack_pairs == 10]
    assert len(kids) == 2 and all(r.cogs_per_unit == Decimal(50000) for r in kids)
    assert all(r.effective_from == date(2026, 1, 1) for r in rows)
    assert all(r.packaging_per_unit == 0 and r.inbound_logistics_per_unit == 0 for r in rows)
    assert len({r.sku_id for r in rows}) == 45
    draft = [r for r in rows if r.status == "DRAFT"]
    assert len(draft) == 1 and draft[0].sku_id == "1736571478276015175"


def test_parse_cogs_rejects_duplicates(tmp_path):
    p = tmp_path / "c.csv"
    hdr = "product_id,sku_id,seller_sku,product_title,status,list_price_idr,pack_pairs,cogs_per_unit_idr,packaging_per_unit_idr,inbound_logistics_per_unit_idr,effective_from,note\n"
    p.write_text(hdr + "1,9,,t,ACTIVATE,1,5,25000,0,0,2026-01-01,\n1,9,,t,ACTIVATE,1,5,26000,0,0,2026-01-01,\n")
    with pytest.raises(ValueError):
        parse_cogs_csv(p)
    p.write_text(hdr + "1,9,,t,ACTIVATE,1,5,25000,0,0,2026-01-01,\n1,9,,t,ACTIVATE,1,5,26000,,,2026-03-01,x\n")
    rows = parse_cogs_csv(p)
    assert len(rows) == 2 and rows[1].packaging_per_unit == 0 and rows[1].note == "x"
