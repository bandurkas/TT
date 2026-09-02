"""Windsor.ai GMV Max ingest. The rule under test throughout: absence is never spend of zero."""
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from src.domain.ads import windsor as W
from src.domain.reports import WINDSOR_SCOPE
from src.integrations.windsor.client import FIELDS, WindsorClient, WindsorError

SHOP = NS(id=1, timezone="Asia/Jakarta", currency="IDR")


def client(payload, capture=None):
    def opener(url, timeout):
        if capture is not None:
            capture.append(url)
        return json.dumps(payload).encode()
    return WindsorClient("k", opener=opener)


# --- client ------------------------------------------------------------------------------------
def test_client_requests_a_gmv_max_field_and_never_leaks_the_key():
    urls = []
    rows, meta = client({"data": [{"date": "2026-08-26", "account_id": "76583", "campaign_id": "1",
                                    "gmv_max_ads_spend": 5}]}, urls).fetch_gmv_max(date(2026, 8, 26), date(2026, 8, 26))
    assert rows and meta["rows"] == 1 and meta["date_from"] == "2026-08-26"
    # plain `spend` returns nothing for this advertiser; the GMV Max field must always be requested
    assert "gmv_max_ads_spend" in urls[0]
    assert "api_key=k" in urls[0] and "api_key=k" not in meta["url"] and "api_key=%2A%2A%2A" in meta["url"]
    assert meta["fields"] == list(FIELDS)


def test_client_refuses_everything_that_could_be_mistaken_for_zero_spend():
    # an unknown field name answers {"data": []} with HTTP 200 — rows are simply absent, not zero
    rows, meta = client({"data": []}).fetch_gmv_max(date(2026, 8, 1), date(2026, 8, 2))
    assert rows == [] and meta["rows"] == 0          # empty is data-less, and the caller writes nothing
    with pytest.raises(WindsorError, match="future"):
        client({"error": "date_from is in the future"}).fetch_gmv_max(date(2026, 8, 1), date(2026, 8, 1))
    with pytest.raises(WindsorError, match="no 'data' list"):
        client({"whatever": 1}).fetch_gmv_max(date(2026, 8, 1), date(2026, 8, 1))
    with pytest.raises(WindsorError, match="missing"):   # renamed/dropped field = contract change
        client({"data": [{"date": "2026-08-01", "campaign_id": "1"}]}).fetch_gmv_max(
            date(2026, 8, 1), date(2026, 8, 1))
    # only the two fields a row cannot be grouped without are fatal
    with pytest.raises(WindsorError, match=r"empty \['campaign_id'\]"):
        client({"data": [{"date": "2026-08-01", "account_id": "1", "campaign_id": "  ",
                          "gmv_max_ads_spend": 1}]}).fetch_gmv_max(date(2026, 8, 1), date(2026, 8, 1))
    # a null spend does NOT stop the request: it must cost its own day only, never the window
    rows2, _ = client({"data": [{"date": "2026-08-01", "account_id": "1", "campaign_id": "1",
                                 "gmv_max_ads_spend": None}]}).fetch_gmv_max(date(2026, 8, 1), date(2026, 8, 1))
    assert rows2[0]["gmv_max_ads_spend"] is None
    with pytest.raises(WindsorError, match="Empty range"):
        client({"data": []}).fetch_gmv_max(date(2026, 8, 2), date(2026, 8, 1))

    def boom(url, timeout):
        raise TimeoutError("timed out")
    with pytest.raises(WindsorError, match="request failed"):
        WindsorClient("k", opener=boom).fetch_gmv_max(date(2026, 8, 1), date(2026, 8, 1))
    with pytest.raises(WindsorError):
        WindsorClient("")


# --- window ------------------------------------------------------------------------------------
def test_window_ends_yesterday_in_shop_time():
    """02:18 WIB on 2 Sep is 19:18 UTC on 1 Sep; the connector's own 'today' was still 1 Sep and a
    later date is a hard error, so the window must end on the last day that has ended for the shop."""
    now = datetime(2026, 9, 1, 19, 18, tzinfo=UTC)
    assert W.window("Asia/Jakarta", 7, now) == (date(2026, 8, 26), date(2026, 9, 1))
    assert W.window("Asia/Jakarta", 1, now) == (date(2026, 9, 1), date(2026, 9, 1))
    assert W.window("Asia/Jakarta", 0, now) == (date(2026, 9, 1), date(2026, 9, 1))


# --- ingest ------------------------------------------------------------------------------------
def _stub_hierarchy(monkeypatch):
    """Silence the ad_accounts/campaigns/ad_metrics branch for tests that are about the Cost path."""
    monkeypatch.setattr(W, "_ad_account", lambda *a: NS(id=1))
    monkeypatch.setattr(W, "_campaign", lambda s, acc, cid, name: NS(id=1, external_campaign_id=cid))
    monkeypatch.setattr(W, "_metric", lambda *a: None)


def _session():
    s = MagicMock()
    s.scalar.side_effect = None
    s.scalar.return_value = None
    return s


def test_ingest_writes_only_the_days_the_connector_reported(monkeypatch):
    rows = [
        {"date": "2026-08-30", "account_id": "76583", "account_name": "Lomira.product",
         "campaign_id": "1872852148459778", "campaign": "majority black", "gmv_max_ads_spend": 309660},
        {"date": "2026-08-31", "account_id": "76583", "account_name": "Lomira.product",
         "campaign_id": "1872852148459778", "campaign": "majority black", "gmv_max_ads_spend": 300000},
        {"date": "2026-08-31", "account_id": "76583", "account_name": "Lomira.product",
         "campaign_id": "1874692964779154", "campaign": "moms and girls", "gmv_max_ads_spend": 39256},
    ]
    calls = []

    def fake_record(session, shop_id, day, cost, sku_orders, gross_revenue, observed, tz, **kw):
        calls.append((day, str(cost), kw.get("final"), kw.get("scope"), sku_orders, gross_revenue))
        return {"unchanged": False, "report_id": len(calls)}

    monkeypatch.setattr(W, "record_ad_day", fake_record)
    monkeypatch.setattr(W, "_ad_account", lambda *a: None)          # hierarchy covered separately
    monkeypatch.setattr(W, "_stored", lambda *a: None)
    out = W.ingest(_session(), SHOP, rows, {"rows": 3}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))

    assert out["days"] == 2 and out["written"] == 2 and out["disagreements"] == []
    # the two campaigns of 31 Aug are summed into that day's Cost, and nothing else is touched
    assert calls == [(date(2026, 8, 30), "309660", True, WINDSOR_SCOPE, None, None),
                     (date(2026, 8, 31), "339256", True, WINDSOR_SCOPE, None, None)]
    # 2026-08-29 was not in the response and therefore was never written at all
    assert not any(c[0] == date(2026, 8, 29) for c in calls)


def test_ingest_stores_raw_and_writes_nothing_when_there_are_no_rows():
    s = _session()
    out = W.ingest(s, SHOP, [], {"rows": 0}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert out == {"days": 0, "written": 0, "unchanged": 0, "campaigns": 0,
                   "disagreements": [], "skipped_null_days": [], "note": "no rows"}
    raw = s.add.call_args_list[0].args[0]          # raw payload is kept even when empty (SPEC 2.2)
    assert raw.integration == "windsor" and raw.resource == W.RESOURCE and raw.payload == {"data": []}


def test_ingest_reports_a_material_disagreement_instead_of_hiding_it(monkeypatch):
    rows = [{"date": "2026-08-31", "account_id": "76583", "campaign_id": "1",
             "gmv_max_ads_spend": 339256}]
    monkeypatch.setattr(W, "record_ad_day", lambda *a, **k: {"unchanged": False})
    _stub_hierarchy(monkeypatch)
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("73989"), partial=False, manual=False))
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert out["disagreements"] == [{"date": "2026-08-31", "stored": "73989", "windsor": "339256"}]

    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339250"), partial=False, manual=False))  # tiny drift
    assert W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))["disagreements"] == []


def test_ingest_keeps_the_open_day_partial_and_skips_a_newer_observation(monkeypatch):
    seen = []

    def rec(session, shop_id, day, cost, *a, **kw):
        seen.append((day, kw.get("final")))
        if day == date(2026, 9, 1):
            raise ValueError("A newer or equal observation for this day already exists")
        return {"unchanged": False}

    monkeypatch.setattr(W, "record_ad_day", rec)
    _stub_hierarchy(monkeypatch)
    monkeypatch.setattr(W, "_stored", lambda *a: None)
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "1", "gmv_max_ads_spend": 1},
            {"date": "2026-09-01", "account_id": "1", "campaign_id": "1", "gmv_max_ads_spend": 2}]
    # 09:00 WIB on 1 Sep -> 31 Aug has ended, 1 Sep has not
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 2, 0, tzinfo=UTC))
    assert seen == [(date(2026, 8, 31), True), (date(2026, 9, 1), False)]
    # a newer observation already on file is the normal case on a re-run, not a disagreement
    assert out["written"] == 1 and out["unchanged"] == 1 and out["disagreements"] == []


def test_ads_windsor_job_is_skipped_without_a_key_and_never_reaches_the_network(monkeypatch):
    from apps.worker import scheduler as S
    monkeypatch.setattr(S.settings, "windsor_api_key", "")
    assert S.ads_windsor(MagicMock(), lambda s: NS(shop=SHOP)) == {"skipped": "WINDSOR_API_KEY not configured"}
    assert "ads_windsor" in S.JOBS and S.SLOTS["ads_windsor"] == {"minute": 25}


def test_ads_windsor_job_recomputes_profit_only_when_something_was_written(monkeypatch):
    import src.integrations.windsor.client as C
    from apps.worker import scheduler as S
    monkeypatch.setattr(S.settings, "windsor_api_key", "k")
    monkeypatch.setattr(S.settings, "windsor_backfill_days", 2)
    monkeypatch.setattr(C.WindsorClient, "fetch_gmv_max", lambda self, a, b: ([{"x": 1}], {"m": 1}))
    computed = []
    monkeypatch.setattr(S, "_compute_profit", lambda s, shop: computed.append(shop) or {"profit": "ok"})

    monkeypatch.setattr(W, "ingest", lambda *a, **k: {"written": 0, "days": 2})
    assert "profit" not in S.ads_windsor(MagicMock(), lambda s: NS(shop=SHOP))
    assert computed == []

    monkeypatch.setattr(W, "ingest", lambda *a, **k: {"written": 2, "days": 2})
    assert S.ads_windsor(MagicMock(), lambda s: NS(shop=SHOP))["profit"] == "ok"
    assert computed == [SHOP]


def test_ingest_sums_duplicate_campaign_rows_instead_of_letting_the_last_one_win(monkeypatch):
    """ad_metrics is written per campaign and shop_ad_days is the sum; if the connector splits one
    campaign-day across rows, both must be derived from the same arithmetic."""
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "campaign": "a",
             "gmv_max_ads_spend": 100000},
            {"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "campaign": "a",
             "gmv_max_ads_spend": 200000},
            {"date": "2026-08-31", "account_id": "1", "campaign_id": "c2", "campaign": "b",
             "gmv_max_ads_spend": 39256}]
    metrics, costs = [], []
    monkeypatch.setattr(W, "_ad_account", lambda *a: NS(id=7))
    monkeypatch.setattr(W, "_campaign", lambda s, acc, cid, name: NS(id=hash(cid) % 100,
                                                                     external_campaign_id=cid))
    monkeypatch.setattr(W, "_metric", lambda s, cid, day, spend, cur, at, fin: metrics.append((cid, str(spend))))
    monkeypatch.setattr(W, "_stored", lambda *a: None)
    monkeypatch.setattr(W, "record_ad_day", lambda s, sid, day, cost, *a, **k: costs.append(str(cost)) or {})
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert sorted(x[1] for x in metrics) == ["300000", "39256"]   # c1 summed, not overwritten
    assert costs == ["339256"] and out["campaigns"] == 2


def test_ingest_skips_a_day_that_has_not_moved_so_the_hourly_run_is_a_no_op(monkeypatch):
    """observed_at is inside the content hash, so writing an unchanged day would insert a fresh
    SourceReport every hour and trigger a full profit recompute for nothing."""
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 339256}]
    wrote = []
    _stub_hierarchy(monkeypatch)
    monkeypatch.setattr(W, "record_ad_day", lambda *a, **k: wrote.append(1) or {})
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339256"), partial=False, manual=False))
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    # the day's Cost is left alone, but its per-campaign split is still recorded
    assert wrote == [] and out == {"days": 1, "written": 0, "unchanged": 1, "campaigns": 1,
                                   "disagreements": [], "skipped_null_days": []}
    # same figure, wrong finality -> still written
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339256"), partial=True, manual=False))
    assert W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))["written"] == 1
    assert wrote == [1]
    # same figure, but the day is still flagged manual -> claim it, so it stops being operator-owned
    wrote.clear()
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339256"), partial=False, manual=True))
    assert W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))["written"] == 1


def test_ingest_lets_a_real_validation_failure_fail_the_job(monkeypatch):
    """Only "a newer observation exists" is benign; anything else must not be reported as skipped
    while /health stays green."""
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 1}]
    _stub_hierarchy(monkeypatch)
    monkeypatch.setattr(W, "_stored", lambda *a: None)

    rows = rows + [{"date": "2026-09-01", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 2}]
    seen = []

    def boom(session, shop_id, day, *a, **k):
        seen.append(day)
        if day == date(2026, 8, 31):
            raise ValueError("Cost, SKU orders and gross revenue must be non-negative")
        return {}
    monkeypatch.setattr(W, "record_ad_day", boom)
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    # the bad day fails the job, the good day is still ingested: one bad day must not truncate the
    # window every hour and leave everything after it permanently unwritten
    assert seen == [date(2026, 8, 31), date(2026, 9, 1)]
    assert out["errors"] == ["2026-08-31: Cost, SKU orders and gross revenue must be non-negative"]
    assert out["written"] == 1


def test_redact_removes_the_key_wherever_it_sits():
    from src.integrations.windsor.client import WindsorClient as C
    assert "secret" not in C.redact("https://x/y?api_key=secret&fields=a")
    assert "secret" not in C.redact("https://x/y?fields=a&api_key=secret")
    assert "secret" not in C.redact("https://x/y?a=1&api_key=secret&b=2")


def test_platform_source_never_claims_it_measured_zero_orders():
    """Windsor reports neither SKU orders nor gross revenue. The columns are not nullable, so 0 is
    stored — but the API must return null, not a zero that reads as a measurement."""
    from src.domain import reports as R
    s = MagicMock()
    s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
    s.scalar.side_effect = [None, None]
    s.scalars.return_value.all.return_value = []
    s.execute.return_value.first.return_value = None
    R.record_ad_day(s, 1, date(2026, 8, 31), "339256", None, None,
                    datetime(2026, 9, 1, 15, 30, tzinfo=UTC), "Asia/Jakarta", final=True,
                    scope=R.WINDSOR_SCOPE, label="windsor-gmv-max")
    data = s.add.call_args_list[0].args[0].data
    assert data["figures_unknown"] == ["sku_orders", "gross_revenue"] and "carried_over" not in data
    assert data["sku_orders"] == 0        # stored as 0 (column is NOT NULL) but flagged as unobserved


def test_a_null_spend_costs_its_own_day_and_never_the_window(monkeypatch):
    """One campaign-day with a null spend must not throw away the other good days, and its own day
    must not be written from a partial sum of the campaigns that did report."""
    rows = [{"date": "2026-08-30", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 309660},
            {"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 300000},
            {"date": "2026-08-31", "account_id": "1", "campaign_id": "c2", "gmv_max_ads_spend": None}]
    days = []
    _stub_hierarchy(monkeypatch)
    monkeypatch.setattr(W, "_stored", lambda *a: None)
    monkeypatch.setattr(W, "record_ad_day",
                        lambda s, sid, day, cost, *a, **k: days.append((day, str(cost))) or {})
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert days == [(date(2026, 8, 30), "309660")]   # 31 Aug dropped whole, not written as 300000
    assert out["skipped_null_days"] == ["2026-08-31"] and out["days"] == 1


def test_hierarchy_is_written_even_when_the_days_total_has_not_moved(monkeypatch):
    """A campaign-mix restatement keeps the same sum, and a day first entered by hand has no
    campaigns at all — so ad_metrics must not sit behind the unchanged-day fast path."""
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 200000},
            {"date": "2026-08-31", "account_id": "1", "campaign_id": "c2", "gmv_max_ads_spend": 139256}]
    metrics, wrote = [], []
    monkeypatch.setattr(W, "_ad_account", lambda *a: NS(id=7))
    monkeypatch.setattr(W, "_campaign", lambda s, acc, cid, name: NS(id=1, external_campaign_id=cid))
    monkeypatch.setattr(W, "_metric", lambda s, cid, d, spend, cur, at, fin: metrics.append(str(spend)))
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339256"), partial=False, manual=False))
    monkeypatch.setattr(W, "record_ad_day", lambda *a, **k: wrote.append(1) or {})
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert sorted(metrics) == ["139256", "200000"]   # per-campaign detail recorded
    assert wrote == [] and out["unchanged"] == 1     # the day's Cost itself is left alone
    assert out["campaigns"] == 2


def test_unknown_figures_stay_unknown_when_windsor_restates_the_same_day():
    """Windsor restates days inside its backfill window; "never observed" must not decay into a
    measured 0 just because a previous Windsor row is now the prior record."""
    from src.domain import reports as R
    s = MagicMock()
    s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
    s.scalar.side_effect = [None, None]
    s.scalars.return_value.all.return_value = []
    prior = NS(observed_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
               data={"figures_unknown": ["sku_orders", "gross_revenue"]})
    s.execute.return_value.first.return_value = (NS(sku_orders=0, gross_revenue=R.number("0")), prior)
    R.record_ad_day(s, 1, date(2026, 8, 31), "340000", None, None,
                    datetime(2026, 9, 1, 15, 30, tzinfo=UTC), "Asia/Jakarta", final=True,
                    scope=R.WINDSOR_SCOPE, label="windsor-gmv-max")
    data = s.add.call_args_list[0].args[0].data
    assert data["figures_unknown"] == ["sku_orders", "gross_revenue"] and "carried_over" not in data


def test_figures_a_human_actually_entered_are_carried_not_marked_unknown():
    from src.domain import reports as R
    s = MagicMock()
    s.get.return_value = NS(timezone="Asia/Jakarta", currency="IDR")
    s.scalar.side_effect = [None, None]
    s.scalars.return_value.all.return_value = []
    prior = NS(observed_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC), data={"scope": "manual_entry"})
    s.execute.return_value.first.return_value = (NS(sku_orders=10, gross_revenue=R.number("810904")),
                                                 prior)
    R.record_ad_day(s, 1, date(2026, 8, 31), "340000", None, None,
                    datetime(2026, 9, 1, 15, 30, tzinfo=UTC), "Asia/Jakarta", final=True,
                    scope=R.WINDSOR_SCOPE, label="windsor-gmv-max")
    data = s.add.call_args_list[0].args[0].data
    assert data["carried_over"] == ["sku_orders", "gross_revenue"] and "figures_unknown" not in data
    assert data["sku_orders"] == 10


def test_advertising_summary_returns_null_for_figures_the_source_never_reported():
    from unittest.mock import patch

    from src.domain import reports as R
    day = NS(metric_date=date(2026, 8, 31), cost=R.number("339256"), partial=False,
             sku_orders=0, gross_revenue=R.number("0"), report_id=5, currency="IDR")
    rep = NS(id=5, filename="windsor-gmv-max", sha256="x", observed_at=datetime(2026, 9, 1, tzinfo=UTC),
             timezone="Asia/Jakarta", period_start=day.metric_date, period_end=day.metric_date,
             data={"scope": R.WINDSOR_SCOPE, "figures_unknown": ["sku_orders", "gross_revenue"],
                   "note": "Windsor.ai GMV Max, 2 campaign(s)"})
    s = MagicMock()
    s.scalars.return_value = [rep]
    with patch.object(R, "ad_days", lambda *a: [day]), \
         patch("src.domain.dashboard.loaders.ad_deductions", lambda *a: []):
        out = R.advertising_summary(s, 1, date(2026, 8, 31), date(2026, 8, 31), "Asia/Jakarta")
    d = out["days"][0]
    assert d["cost"] == R.number("339256")
    assert d["sku_orders"] is None and d["gross_revenue"] is None   # stored 0, never measured
    assert d["source"] == R.WINDSOR_SCOPE and out["windsor_days"] == 1
    assert out["source"] == "Windsor.ai GMV Max · Cost"


def test_an_unusable_account_id_is_reported_but_never_costs_the_days_cost(monkeypatch):
    """account_id feeds only the hierarchy. An empty one must not abort the window — but it must not
    pass unnoticed either, which is how the campaign branch went silently missing before."""
    from src.integrations.windsor.client import blank
    assert blank(None) and blank("") and blank("   ") and not blank("76583")

    rows = [{"date": "2026-08-31", "account_id": "  ", "campaign_id": "c1", "gmv_max_ads_spend": 5}]
    wrote = []
    monkeypatch.setattr(W, "_stored", lambda *a: None)
    monkeypatch.setattr(W, "record_ad_day", lambda *a, **k: wrote.append(1) or {})
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert wrote == [1] and out["campaigns"] == 0           # the day's Cost still lands
    assert out["errors"] == ["no usable account_id in the response; campaigns and ad_metrics not written"]


def test_a_null_day_is_an_error_only_when_nothing_is_on_file_for_it(monkeypatch):
    """A day with nothing to fall back on is genuinely missing and must reach /health. A day that
    already has a Cost gained no new information — holding the job red for the whole backfill window
    would mask the next real failure behind a benign one."""
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": None}]
    _stub_hierarchy(monkeypatch)
    monkeypatch.setattr(W, "record_ad_day", lambda *a, **k: {})

    monkeypatch.setattr(W, "_stored", lambda *a: None)
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert out["skipped_null_days"] == ["2026-08-31"]
    assert out["errors"] == ["2026-08-31: null gmv_max_ads_spend and no Cost on file for that day"]
    from apps.worker.scheduler import _collect_errors
    assert "null gmv_max_ads_spend" in _collect_errors(out)[0]   # this is what marks the job failed

    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339256"), partial=False, manual=False))
    quiet = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert quiet["skipped_null_days"] == ["2026-08-31"] and "errors" not in quiet

    # a still-open manual entry IS a fallback: the dashboard flags it as partial already, and
    # Windsor never reports the open day, so calling it missing would fail the job forever
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("100000"), partial=True, manual=True))
    open_day = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert "errors" not in open_day


def test_a_real_rejection_is_reported_before_a_benign_null_day(monkeypatch):
    """/health renders only errors[0], so the most severe thing that happened has to be first."""
    rows = [{"date": "2026-08-30", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": None},
            {"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 5}]
    _stub_hierarchy(monkeypatch)
    monkeypatch.setattr(W, "_stored", lambda *a: None)

    def reject(*a, **k):
        raise ValueError("Cost, SKU orders and gross revenue must be non-negative")
    monkeypatch.setattr(W, "record_ad_day", reject)
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert out["errors"][0].startswith("2026-08-31: Cost, SKU orders")
    assert "null gmv_max_ads_spend" in out["errors"][1]


def test_errors_are_ordered_by_blast_radius(monkeypatch):
    """/health shows one line. An unusable account cost the whole window its campaign detail; a
    rejection cost one day; a null day cost one day's refresh."""
    rows = [{"date": "2026-08-30", "account_id": "  ", "campaign_id": "c1", "gmv_max_ads_spend": None},
            {"date": "2026-08-31", "account_id": "  ", "campaign_id": "c1", "gmv_max_ads_spend": 5}]
    monkeypatch.setattr(W, "_stored", lambda *a: None)

    def reject(*a, **k):
        raise ValueError("Explicit report timezone must match the shop timezone")
    monkeypatch.setattr(W, "record_ad_day", reject)
    errs = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))["errors"]
    assert errs[0].startswith("no usable account_id")
    assert errs[1].startswith("2026-08-31: Explicit report timezone")
    assert errs[2].startswith("2026-08-30: null")


def test_the_ad_account_is_committed_before_any_day_can_roll_it_back(monkeypatch):
    """A rollback inside the day loop would otherwise discard the freshly created AdAccount while
    its id survives on the expunged object, and every later campaign would hit a dead foreign key.
    So the commit has to happen before the first record_ad_day, not merely somewhere."""
    order = []
    s = _session()
    s.scalar.return_value = None                          # no AdAccount on file yet
    s.commit.side_effect = lambda: order.append("commit")
    s.rollback.side_effect = lambda: order.append("rollback")
    monkeypatch.setattr(W, "_campaign", lambda ses, acc, cid, name: NS(id=1, external_campaign_id=cid))
    monkeypatch.setattr(W, "_metric", lambda *a: None)
    monkeypatch.setattr(W, "_stored", lambda *a: None)

    def reject(*a, **k):
        order.append("record")
        raise ValueError("Cost, SKU orders and gross revenue must be non-negative")
    monkeypatch.setattr(W, "record_ad_day", reject)
    rows = [{"date": "2026-08-30", "account_id": "76583", "campaign_id": "c1", "gmv_max_ads_spend": 1},
            {"date": "2026-08-31", "account_id": "76583", "campaign_id": "c1", "gmv_max_ads_spend": 2}]
    W.ingest(s, SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    # raw payload, then the account — both durable before the first day is attempted
    assert order[:2] == ["commit", "commit"]
    assert order.index("record") > 1 and "rollback" in order


def test_per_campaign_spend_is_not_written_when_the_days_cost_was_rejected(monkeypatch):
    """ad_metrics must never outlive the Cost it splits, or the two disagree permanently and the
    disagreement is re-committed every hour."""
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 5}]
    metrics = []
    monkeypatch.setattr(W, "_ad_account", lambda *a: NS(id=1))
    monkeypatch.setattr(W, "_campaign", lambda s, acc, cid, name: NS(id=1, external_campaign_id=cid))
    monkeypatch.setattr(W, "_metric", lambda s, cid, d, spend, *a: metrics.append(str(spend)))
    monkeypatch.setattr(W, "_stored", lambda *a: None)

    def reject(*a, **k):
        raise ValueError("Cost, SKU orders and gross revenue must be non-negative")
    monkeypatch.setattr(W, "record_ad_day", reject)
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert metrics == [] and out["campaigns"] == 0 and out["errors"]
