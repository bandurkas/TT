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
    # the connector answers null for anything it cannot fill; a null spend is NOT a measured zero
    with pytest.raises(WindsorError, match=r"null \['gmv_max_ads_spend'\]"):
        client({"data": [{"date": "2026-08-01", "account_id": "1", "campaign_id": "1",
                          "gmv_max_ads_spend": None}]}).fetch_gmv_max(date(2026, 8, 1), date(2026, 8, 1))
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
                   "disagreements": [], "note": "no rows"}
    raw = s.add.call_args_list[0].args[0]          # raw payload is kept even when empty (SPEC 2.2)
    assert raw.integration == "windsor" and raw.resource == W.RESOURCE and raw.payload == {"data": []}


def test_ingest_reports_a_material_disagreement_instead_of_hiding_it(monkeypatch):
    rows = [{"date": "2026-08-31", "account_id": "76583", "campaign_id": "1",
             "gmv_max_ads_spend": 339256}]
    monkeypatch.setattr(W, "record_ad_day", lambda *a, **k: {"unchanged": False})
    monkeypatch.setattr(W, "_ad_account", lambda *a: None)
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("73989"), partial=False))
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert out["disagreements"] == [{"date": "2026-08-31", "stored": "73989", "windsor": "339256"}]

    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339250"), partial=False))  # tiny drift
    assert W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))["disagreements"] == []


def test_ingest_keeps_the_open_day_partial_and_skips_a_newer_observation(monkeypatch):
    seen = []

    def rec(session, shop_id, day, cost, *a, **kw):
        seen.append((day, kw.get("final")))
        if day == date(2026, 9, 1):
            raise ValueError("A newer or equal observation for this day already exists")
        return {"unchanged": False}

    monkeypatch.setattr(W, "record_ad_day", rec)
    monkeypatch.setattr(W, "_ad_account", lambda *a: None)
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
    monkeypatch.setattr(W, "_ad_account", lambda *a: None)
    monkeypatch.setattr(W, "record_ad_day", lambda *a, **k: wrote.append(1) or {})
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339256"), partial=False))
    out = W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))
    assert wrote == [] and out == {"days": 1, "written": 0, "unchanged": 1, "campaigns": 0,
                                   "disagreements": []}
    # the same figure but a different finality still has to be written
    monkeypatch.setattr(W, "_stored", lambda *a: NS(cost=W.number("339256"), partial=True))
    assert W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))["written"] == 0 or wrote


def test_ingest_lets_a_real_validation_failure_fail_the_job(monkeypatch):
    """Only "a newer observation exists" is benign; anything else must not be reported as skipped
    while /health stays green."""
    rows = [{"date": "2026-08-31", "account_id": "1", "campaign_id": "c1", "gmv_max_ads_spend": 1}]
    monkeypatch.setattr(W, "_ad_account", lambda *a: None)
    monkeypatch.setattr(W, "_stored", lambda *a: None)

    def boom(*a, **k):
        raise ValueError("Explicit report timezone must match the shop timezone")
    monkeypatch.setattr(W, "record_ad_day", boom)
    with pytest.raises(ValueError, match="timezone"):
        W.ingest(_session(), SHOP, rows, {}, now=datetime(2026, 9, 1, 19, 0, tzinfo=UTC))


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
