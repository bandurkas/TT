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
    detail = O.breakdown(o, p, [], [])
    lines = {r['key']: r for r in detail['lines']}
    assert lines['contribution_profit']['amount'] is None
    assert lines['net_seller_revenue']['amount'] is not None


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


def test_record_manual_ad_day_validation_and_payload(monkeypatch):
    from datetime import UTC, date, datetime, timedelta
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    import pytest

    from src.domain import reports as R
    session = MagicMock()
    session.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
    session.scalar.return_value = None
    session.execute.return_value.first.return_value = None
    now = datetime(2026, 8, 31, 13, 0, tzinfo=UTC)  # 20:00 Jakarta, 31 Aug (past)
    with pytest.raises(ValueError):
        R.record_manual_ad_day(session, 1, date(2026, 9, 1), 1, 0, 0, now, "Asia/Jakarta")  # future
    with pytest.raises(ValueError):
        R.record_manual_ad_day(session, 1, date(2026, 8, 31), 1, 0, 0, now, "Asia/Jakarta", final=True)  # not over
    with pytest.raises(ValueError):
        R.record_manual_ad_day(session, 1, date(2026, 8, 31), -1, 0, 0, now, "Asia/Jakarta")
    with pytest.raises(ValueError):
        R.record_manual_ad_day(session, 1, date(2026, 8, 31), 1, 0, 0, now, "UTC")
    with pytest.raises(ValueError):
        R.record_manual_ad_day(session, 1, date(2026, 9, 1), 1, 0, 0, now + timedelta(hours=1), "Asia/Jakarta")
    out = R.record_manual_ad_day(session, 1, date(2026, 8, 31), "421192", 9, "735034", now, "Asia/Jakarta", note="20:00 screen")
    assert out["unchanged"] is False and out["partial"] is True and out["period"] == ["2026-08-31", "2026-08-31"]
    report = session.add.call_args_list[0].args[0]
    assert report.data["scope"] == "manual_entry" and report.data["days"][0]["cost"] == "421192"
    assert report.filename.startswith("manual-entry 2026-08-31 @ 20:00")
    day = session.add.call_args_list[1].args[0]
    assert day.cost == R.number("421192") and day.partial is True
    # completed day entered next morning with final=True -> not partial
    session.reset_mock(); session.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
    session.scalar.return_value = None; session.execute.return_value.first.return_value = None
    out2 = R.record_manual_ad_day(session, 1, date(2026, 8, 30), 1, 0, 0, now, "Asia/Jakarta", final=True)
    assert out2["partial"] is False
    # older-or-equal observation is rejected
    session.execute.return_value.first.return_value = (NS(), NS(observed_at=now))
    with pytest.raises(ValueError):
        R.record_manual_ad_day(session, 1, date(2026, 8, 30), 2, 0, 0, now, "Asia/Jakarta", final=True)


def test_manual_ad_day_guards_against_period_totals_and_thinner_records():
    """The two live-data corruptions of 2026-09-01: a month's totals typed into one day, and a
    full record replaced by a near-empty one. Both must be refused, both overridable."""
    from datetime import UTC, date, datetime
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    import pytest

    from src.domain import reports as R
    day = date(2026, 9, 1)
    now = datetime(2026, 9, 1, 15, 30, tzinfo=UTC)  # 22:30 Jakarta, same day

    def session_with(actual=None, prior=None, recent=()):
        s = MagicMock()
        s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
        s.scalar.side_effect = [None, actual]  # digest lookup, then analytics_shop_daily
        s.scalars.return_value.all.return_value = list(recent)  # recent daily Cost history
        s.execute.return_value.first.return_value = ((prior, NS(observed_at=datetime(2026, 9, 1, 14, 0, tzinfo=UTC)))
                                                     if prior is not None else None)
        return s

    def call(s, cost, orders, gross, **kw):
        return R.record_manual_ad_day(s, 1, day, cost, orders, gross, now, "Asia/Jakarta", **kw)

    actual = NS(units=10, gmv=R.number("825000"))
    # 1. a month's figures entered as one day
    with pytest.raises(R.NeedsConfirmation, match="SKU orders 87"):
        call(session_with(actual), "5062670", 87, "8636752")
    # GMV alone trips it too, when orders happen to look sane
    with pytest.raises(R.NeedsConfirmation, match=r"Gross revenue 8636752 is over 2x the 825000 GMV"):
        call(session_with(actual), "5062670", 10, "8636752")
    # the real day passes untouched
    out = call(session_with(actual), "450000", 10, "810904")
    assert out["unchanged"] is False and out["partial"] is True
    # and the operator can still override
    out = call(session_with(actual), "5062670", 87, "8636752", confirm=True)
    assert out["unchanged"] is False

    # 2. a fuller record replaced by a thinner one
    prior = NS(cost=R.number("450000"), sku_orders=10, gross_revenue=R.number("810904"))
    with pytest.raises(R.NeedsConfirmation, match=r"Cost 2000 is far below the 450000 "):
        call(session_with(actual, prior), "2000", 10, "810904")
    with pytest.raises(R.NeedsConfirmation, match="blank SKU orders and gross revenue"):
        call(session_with(actual, prior), "450000", 0, "0")
    # a normal intraday update — cost grew, figures kept — passes
    assert call(session_with(actual, prior), "460000", 10, "820000")["unchanged"] is False
    # no actuals yet for the day: the period-total check cannot fire, and must not block a first entry
    assert call(session_with(None), "450000", 10, "810904")["unchanged"] is False


def test_manual_ad_day_cost_spike_is_caught_without_any_analytics_for_the_day():
    """The dangerous case the actuals-based checks cannot see: a period's Cost as the FIRST entry of
    a day, with SKU orders and gross revenue left blank. Only Cost feeds net profit, so Cost needs a
    baseline that exists the moment the day opens — the recent daily median, not analytics."""
    from datetime import UTC, date, datetime
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    import pytest

    from src.domain import reports as R
    day, now = date(2026, 9, 1), datetime(2026, 9, 1, 15, 30, tzinfo=UTC)
    history = ["450000", "421192", "480000", "398000", "512000", "455000", "430000"]

    def session_with(recent=(), actual=None):
        s = MagicMock()
        s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
        s.scalar.side_effect = [None, actual]
        s.scalars.return_value.all.return_value = list(recent)
        s.execute.return_value.first.return_value = None  # nothing recorded for the day yet
        return s

    def call(s, cost, **kw):
        return R.record_manual_ad_day(s, 1, day, cost, None, None, now, "Asia/Jakarta", **kw)

    with pytest.raises(R.NeedsConfirmation, match=r"Cost 5062670 is over 4x the 450000 median"):
        call(session_with(history), "5062670")
    # the real day passes, and so does a plausible ramp-up
    assert call(session_with(history), "450000")["unchanged"] is False
    assert call(session_with(history), "900000")["unchanged"] is False
    # too little history: a median of two days means nothing, so the check stands down
    assert call(session_with(["450000", "421192"]), "5062670")["unchanged"] is False
    # zero-spend days are excluded in SQL, so a pause in advertising cannot empty the window and
    # disarm the check on the day spend resumes — the query must carry that filter itself
    s = session_with(history)
    call(s, "450000")
    where = str(s.scalars.call_args.args[0])
    assert "shop_ad_days.cost > " in where and "shop_ad_days.currency = shops.currency" in where
    # and it stays overridable
    assert call(session_with(history), "5062670", confirm=True)["unchanged"] is False


def test_manual_ad_day_omitted_figures_keep_the_day_instead_of_blanking_it():
    """The operator enters Cost several times a day; the form clears the other two fields after each
    apply. Omission must mean 'leave as is' — blanking has to be typed as an explicit 0."""
    from datetime import UTC, date, datetime
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    import pytest

    from src.domain import reports as R
    day, now = date(2026, 9, 1), datetime(2026, 9, 1, 15, 30, tzinfo=UTC)

    def session_with(prior):
        s = MagicMock()
        s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
        s.scalar.side_effect = [None, NS(units=10, gmv=R.number("825000"))]
        s.scalars.return_value.all.return_value = []
        s.execute.return_value.first.return_value = (prior, NS(observed_at=datetime(2026, 9, 1, 14, 0, tzinfo=UTC)))
        return s

    prior = NS(cost=R.number("450000"), sku_orders=10, gross_revenue=R.number("810904"))
    s = session_with(prior)
    out = R.record_manual_ad_day(s, 1, day, "460000", None, None, now, "Asia/Jakarta")
    assert out["unchanged"] is False
    assert prior.cost == R.number("460000")
    assert prior.sku_orders == 10 and prior.gross_revenue == R.number("810904")
    report = s.add.call_args_list[0].args[0]
    assert report.data["sku_orders"] == 10 and report.data["reported_gross_revenue"] == "810904"

    # an explicit 0 still trips the blanking guard
    prior2 = NS(cost=R.number("450000"), sku_orders=10, gross_revenue=R.number("810904"))
    with pytest.raises(R.NeedsConfirmation, match="blank SKU orders and gross revenue"):
        R.record_manual_ad_day(session_with(prior2), 1, day, "460000", 0, 0, now, "Asia/Jakarta")

    # with no record for the day at all, omission means zero, as before
    s3 = MagicMock()
    s3.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
    s3.scalar.side_effect = [None, None]
    s3.scalars.return_value.all.return_value = []
    s3.execute.return_value.first.return_value = None
    R.record_manual_ad_day(s3, 1, day, "450000", None, None, now, "Asia/Jakarta")
    assert s3.add.call_args_list[0].args[0].data["sku_orders"] == 0


def test_manual_ad_day_records_which_figures_were_carried_over():
    """An omitted figure is inherited, not observed. Under final=True it silently becomes the day's
    closing number, so the audit trail has to say it was never read off the screen again."""
    from datetime import UTC, date, datetime
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    from src.domain import reports as R
    now = datetime(2026, 9, 1, 15, 30, tzinfo=UTC)  # 22:30 Jakarta on the 1st -> 31 Aug is over

    def session_with(prior):
        s = MagicMock()
        s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
        s.scalar.side_effect = [None, None]
        s.scalars.return_value.all.return_value = []
        s.execute.return_value.first.return_value = (prior, NS(observed_at=datetime(2026, 9, 1, 14, 0, tzinfo=UTC)))
        return s

    prior = NS(cost=R.number("450000"), sku_orders=10, gross_revenue=R.number("810904"))
    s = session_with(prior)
    R.record_manual_ad_day(s, 1, date(2026, 8, 31), "470000", None, None, now, "Asia/Jakarta", final=True)
    data = s.add.call_args_list[0].args[0].data
    assert data["final"] is True and data["carried_over"] == ["sku_orders", "gross_revenue"]

    # figures actually typed in are not flagged
    s2 = session_with(NS(cost=R.number("450000"), sku_orders=10, gross_revenue=R.number("810904")))
    R.record_manual_ad_day(s2, 1, date(2026, 8, 31), "470000", 11, "820000", now, "Asia/Jakarta", final=True)
    assert "carried_over" not in s2.add.call_args_list[0].args[0].data


def test_manual_ad_day_confirmed_override_is_recorded_in_the_audit_trail():
    from datetime import UTC, date, datetime
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    from src.domain import reports as R
    s = MagicMock()
    s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
    s.scalar.side_effect = [None, None]
    s.execute.return_value.first.return_value = None
    R.record_manual_ad_day(s, 1, date(2026, 9, 1), "5062670", 87, "8636752",
                           datetime(2026, 9, 1, 15, 30, tzinfo=UTC), "Asia/Jakarta", confirm=True)
    report = s.add.call_args_list[0].args[0]
    assert report.data["confirmed_override"] is True


def test_coverage_source_labels_manual(monkeypatch):
    from datetime import UTC, date, datetime
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    from src.domain import reports as R
    rows = [NS(metric_date=date(2026, 8, 31), cost=R.number(73989), partial=True, sku_orders=1,
               gross_revenue=R.number(1), report_id=1),
            NS(metric_date=date(2026, 9, 1), cost=R.number(421192), partial=True, sku_orders=9,
               gross_revenue=R.number(735034), report_id=4)]
    reps = [NS(id=1, filename="Campaign overview.xlsx", sha256="a", observed_at=datetime(2026, 8, 30, tzinfo=UTC),
               timezone="Asia/Jakarta", period_start=date(2025, 8, 31), period_end=date(2026, 8, 31),
               data={"scope": "shop_overview"}),
            NS(id=4, filename="manual-entry 2026-09-01 @ 20:00 Asia/Jakarta", sha256="b",
               observed_at=datetime(2026, 9, 1, 13, tzinfo=UTC), timezone="Asia/Jakarta",
               period_start=date(2026, 9, 1), period_end=date(2026, 9, 1), data={"scope": "manual_entry", "note": "n"})]
    session = MagicMock()
    monkeypatch.setattr(R, "ad_days", lambda s, sid: rows)
    session.scalars.return_value = reps
    monkeypatch.setattr("src.domain.dashboard.loaders.ad_deductions", lambda *a: [])
    out = R.advertising_summary(session, 1, date(2026, 8, 31), date(2026, 9, 1), "Asia/Jakarta")
    assert [d["source"] for d in out["days"]] == ["shop_overview", "manual_entry"]
    assert out["days"][1]["note"] == "n" and out["manual_days"] == 1 and "manual" in out["source"]
