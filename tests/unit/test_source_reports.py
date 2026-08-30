from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from src.domain.dashboard import orders as O
from src.domain.profit.jobs import compute_from_inputs
from src.domain.reports import ADS_HEADERS, coverage, parse_ads
from tests.unit.test_order_journal import sample
from tests.unit.test_profit_jobs import NOW, ctx, inputs, jkt, order, record, settlement


def report():
    return {"Sheet1": {1: dict(zip("ABCDEFG", ADS_HEADERS, strict=True)),
        2: dict(zip("ABCDEFG", ["2026-08-01 00:00:00", "100", "1", "100", "250", "2.50", "IDR"], strict=True)),
        3: dict(zip("ABCDEFG", ["2026-08-02 00:00:00", "0", "0", "0", "0", "0", "IDR"], strict=True)),
        4: dict(zip("ABCDEFG", ["-", "100", "1", "100", "250", "2.50", "IDR"], strict=True))}}


def test_import_total_not_double_counted_and_zero_is_covered():
    start, end, data = parse_ads(report(), "IDR")
    assert (start, end) == (date(2026, 8, 1), date(2026, 8, 2))
    assert data["cost"] == "100" and len(data["days"]) == 2
    assert data["days"][1]["cost"] == "0"


@pytest.mark.parametrize("row,col,value", [(4, "B", "101"), (3, "A", "2026-08-01 00:00:00"),
    (3, "A", "2026-08-03 00:00:00"), (2, "G", "USD"), (2, "B", "NaN"), (2, "B", "-1")])
def test_bad_report_rejected(row, col, value):
    sheets = report()
    sheets["Sheet1"][row][col] = value
    with pytest.raises(ValueError):
        parse_ads(sheets, "IDR")


def test_missing_day_not_zero_and_partial_stays_partial():
    rows = [NS(metric_date=date(2026, 8, 1), cost=D(0), partial=False),
            NS(metric_date=date(2026, 8, 2), cost=D(100), partial=True)]
    assert coverage(rows, date(2026, 8, 1), date(2026, 8, 2))["status"] == "partial"
    out = coverage(rows, date(2026, 8, 1), date(2026, 8, 3))
    assert out["cost"] is None and out["known_cost"] == 100
    assert out["missing_days"] == ["2026-08-03"]


def test_gmv_pay_never_becomes_cost_and_reported_zero_changes_version():
    inp = inputs([ctx(order(), rec=record())], [settlement("pay", jkt(2026, 8, 18), D(-10000))])
    a = compute_from_inputs(inp, NOW)[0]
    assert not a.snapshot["ad_cost_known"] and a.profit.allocated_ad_cost == 0
    inp.advertising = [NS(metric_date=date(2026, 8, 18), cost=D(0), currency="IDR", partial=False, report_id=1)]
    b = compute_from_inputs(inp, NOW)[0]
    assert b.snapshot["ad_cost_known"] and b.hash != a.hash


def test_unknown_ad_or_cost_masks_profit_not_only_expense():
    o, p, _ = sample()
    p.inputs_snapshot["ad_cost_known"] = False
    out = O.order_row(o, p, [])
    assert out["amounts"]["ad_cost"] is None and out["amounts"]["net_profit"] is None
    assert out["amounts"]["profit_share"] is None
    p.inputs_snapshot.update(ad_cost_known=True, cogs_missing=True, cogs_default_used=False)
    out = O.order_row(o, p, [])
    assert out["amounts"]["costs"] is None and out["amounts"]["net_profit"] is None


def test_incomplete_profit_is_hidden_in_waterfall_and_insights():
    from src.domain.dashboard.compute import Totals, waterfall
    from src.domain.dashboard.insights import findings
    _, p, _ = sample()
    p.inputs_snapshot["ad_cost_known"] = False
    steps = {r["key"]: r for r in waterfall([p])["steps"]}
    assert steps["ad_deductions_blended"]["amount"] is None
    assert steps["net_profit"]["amount"] is None
    cur = Totals(net_profit=D(100), ad_cost=D(10), net_seller_revenue=D(200), contribution=D(110), ad_cost_known=False)
    prev = Totals(net_profit=D(50), ad_cost_known=False)
    assert not findings(cur, prev, D('.1'), [], [], {}, 5)
    cur.ad_cost_known, cur.profit_inputs_known = True, False
    assert not findings(cur, prev, D('.1'), [], [], {}, 5)
    from src.domain.dashboard.compute import unit_economics
    cur.units = 1
    assert unit_economics(cur)['cogs_per_unit'] is None
    assert unit_economics(cur)['contribution_per_unit'] is None
    p.inputs_snapshot.update(cogs_missing=True, cogs_default_used=False)
    steps = {r['key']: r for r in waterfall([p])['steps']}
    assert steps['contribution_before_ads']['amount'] is None
    assert steps['cogs']['amount'] is None


def test_waterfall_calendar_cost_includes_unallocated_spend():
    from src.domain.dashboard.compute import waterfall
    _, p, _ = sample()
    steps = {r["key"]: r for r in waterfall([p], {"cost": D(50000)})["steps"]}
    assert steps["ad_deductions_blended"]["amount"] == -50000
    assert steps["net_profit"]["amount"] == p.contribution_profit - D(50000)
