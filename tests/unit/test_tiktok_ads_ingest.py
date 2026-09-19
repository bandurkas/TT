"""TikTok Ads GMV Max ingest. What matters here, beyond the Windsor rules it inherits: both
advertisers are read, the open day survives as a timestamped reading, and platform attribution never
leaks into the shop's own figures."""
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from src.domain.ads import tiktok as T
from src.domain.reports import TIKTOK_SCOPE
from src.integrations.tiktok_ads import gmv_max

SHOP = NS(id=1, timezone="Asia/Jakarta", currency="IDR")
NOW = datetime(2026, 9, 9, 13, 49, tzinfo=UTC)      # 20:49 in Jakarta


def _session():
    s = MagicMock()
    s.scalar.side_effect = None
    s.scalar.return_value = None
    return s


def _row(day, cid, cost, adv="7658353454934671368", orders=0, rev=0, name=None):
    return {"date": date.fromisoformat(day), "advertiser_id": adv, "campaign_id": cid,
            "campaign": name, "cost": Decimal(str(cost)), "ad_orders": orders,
            "ad_revenue": Decimal(str(rev))}


# --- window ------------------------------------------------------------------------------------
def test_window_ends_today_not_yesterday():
    """The whole reason for this source: Windsor's clock trails the shop's and its window stops at
    yesterday, leaving the day in progress to a human."""
    start, end = T.window("Asia/Jakarta", 3, now=NOW)
    assert end == date(2026, 9, 9) and start == date(2026, 9, 7)


def test_window_uses_the_shop_timezone_not_utc():
    # 17:30 UTC is already the next day in Jakarta (UTC+7)
    _, end = T.window("Asia/Jakarta", 1, now=datetime(2026, 9, 9, 17, 30, tzinfo=UTC))
    assert end == date(2026, 9, 10)


# --- grouping ----------------------------------------------------------------------------------
def test_by_day_sums_both_advertisers_into_one_day():
    """Spend lives in two advertiser accounts against the same store; a day's Cost is their sum."""
    rows = [_row("2026-09-08", "A", 100, adv="1"), _row("2026-09-08", "B", 50, adv="2"),
            _row("2026-09-08", "A", 7, adv="1")]
    days = T.by_day(rows)
    assert set(days) == {date(2026, 9, 8)}
    assert days[date(2026, 9, 8)]["A"]["cost"] == Decimal("107")
    assert days[date(2026, 9, 8)]["B"]["cost"] == Decimal("50")


# --- ingest ------------------------------------------------------------------------------------
def _capture(monkeypatch):
    calls = []

    def fake_record(session, shop_id, day, cost, sku_orders, gross_revenue, observed, tz, **kw):
        calls.append({"day": day, "cost": str(cost), "final": kw.get("final"),
                      "scope": kw.get("scope"), "orders": sku_orders, "revenue": gross_revenue,
                      "observed": observed})
        return {"unchanged": False, "report_id": len(calls)}

    monkeypatch.setattr(T, "record_ad_day", fake_record)
    monkeypatch.setattr(T, "_stored", lambda *a: None)
    monkeypatch.setattr(T, "_absent_spend", lambda *a: Decimal(0))
    monkeypatch.setattr(T, "_account", lambda *a: NS(id=9))
    monkeypatch.setattr(T, "_campaign", lambda *a: NS(id=99))
    monkeypatch.setattr(T, "_metric", lambda *a, **k: None)
    return calls


def test_open_day_is_written_partial_and_carries_the_reading_time(monkeypatch):
    calls = _capture(monkeypatch)
    rows = [_row("2026-09-08", "A", 126687), _row("2026-09-09", "A", 91382)]
    out = T.ingest(_session(), SHOP, rows, {}, now=NOW)

    closed, open_day = calls[0], calls[1]
    assert closed["day"] == date(2026, 9, 8) and closed["final"] is True
    # today is a reading, not a settled figure: never final, and stamped with the moment it was taken
    assert open_day["day"] == date(2026, 9, 9) and open_day["final"] is False
    assert open_day["observed"] == NOW and open_day["cost"] == "91382"
    assert out["as_of"] == NOW.isoformat() and out["written"] == 2


def test_platform_attribution_never_reaches_the_shop_figures(monkeypatch):
    """Ads-reported orders/revenue are the platform's attribution, not the shop's (SPEC §7)."""
    calls = _capture(monkeypatch)
    T.ingest(_session(), SHOP, [_row("2026-09-08", "A", 100, orders=5, rev=999)], {}, now=NOW)
    assert calls[0]["orders"] is None and calls[0]["revenue"] is None


def test_a_day_that_has_not_moved_is_not_rewritten(monkeypatch):
    """At a 15-minute cadence an unconditional write would insert a SourceReport every run."""
    calls = _capture(monkeypatch)
    monkeypatch.setattr(T, "_stored", lambda *a: NS(cost=Decimal("126687"), partial=False, manual=False))
    out = T.ingest(_session(), SHOP, [_row("2026-09-08", "A", 126687)], {}, now=NOW)
    assert out["unchanged"] == 1 and out["written"] == 0 and calls == []


def test_a_moved_open_day_is_rewritten_even_though_the_stored_row_is_also_partial(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setattr(T, "_stored", lambda *a: NS(cost=Decimal("80000"), partial=True, manual=False))
    out = T.ingest(_session(), SHOP, [_row("2026-09-09", "A", 91382)], {}, now=NOW)
    assert out["written"] == 1 and calls[0]["cost"] == "91382" and calls[0]["final"] is False


def test_a_large_restatement_is_reported_not_hidden(monkeypatch):
    _capture(monkeypatch)
    monkeypatch.setattr(T, "_stored", lambda *a: NS(cost=Decimal("10000"), partial=False, manual=False))
    out = T.ingest(_session(), SHOP, [_row("2026-09-08", "A", 126687)], {}, now=NOW)
    assert out["disagreements"] == [{"date": "2026-09-08", "stored": "10000", "tiktok": "126687"}]


def test_no_rows_writes_nothing(monkeypatch):
    _capture(monkeypatch)
    out = T.ingest(_session(), SHOP, [], {}, now=NOW)
    assert out["written"] == 0 and out["days"] == 0 and out["note"] == "no rows"


def test_scope_marks_the_provenance(monkeypatch):
    calls = _capture(monkeypatch)
    T.ingest(_session(), SHOP, [_row("2026-09-08", "A", 1)], {}, now=NOW)
    assert calls[0]["scope"] == TIKTOK_SCOPE


# --- fetch -------------------------------------------------------------------------------------
class FakeClient:
    def __init__(self, stores_by_adv, report_by_adv, names=None, fail=None):
        self._stores, self._report = stores_by_adv, report_by_adv
        self._names, self._fail = names or {}, fail

    def request(self, path, params, resource=""):
        if path == "/store/list/":
            adv = params["advertiser_id"]
            if self._fail == adv:
                raise RuntimeError("boom")
            return {"stores": [{"store_id": s} for s in self._stores.get(adv, [])]}
        raise AssertionError(path)

    def paginate(self, path, params, resource="", page_size=100):
        return iter(self._names.get(params["advertiser_id"], []))

    def iter_gmv_max_report(self, adv, stores, dims, metrics, start, end, page_size=200):
        return iter(self._report.get(adv, []))


def _rep(day, cid, cost, orders=0, rev=0):
    return {"dimensions": {"campaign_id": cid, "stat_time_day": f"{day} 00:00:00"},
            "metrics": {"cost": str(cost), "orders": str(orders), "gross_revenue": str(rev)}}


def test_fetch_reads_every_advertiser_because_one_of_them_looks_empty():
    """`/campaign/get/` returns 0 campaigns for the account that holds every live GMV Max campaign;
    reading only the account that looks populated loses most of the spend."""
    c = FakeClient({"1": ["S"], "2": ["S"]},
                   {"1": [_rep("2026-09-08", "A", 100)], "2": [_rep("2026-09-08", "B", 25)]})
    rows, meta = gmv_max.fetch(c, ["1", "2"], date(2026, 9, 8), date(2026, 9, 8))
    assert {r["advertiser_id"] for r in rows} == {"1", "2"}
    assert sum(r["cost"] for r in rows) == Decimal("125")
    assert meta["advertisers"] == {"1": ["S"], "2": ["S"]}


def test_fetch_raises_rather_than_return_a_partial_set():
    """A partial set summed into a day's Cost understates it — the failure this project already paid
    885,857 for. Better a red job than a quietly low figure."""
    c = FakeClient({"1": ["S"]}, {"1": []}, fail="2")
    with pytest.raises(gmv_max.GmvMaxError, match="store list failed for 2"):
        gmv_max.fetch(c, ["1", "2"], date(2026, 9, 8), date(2026, 9, 8))


def test_fetch_skips_a_row_it_cannot_place_without_dropping_the_day():
    c = FakeClient({"1": ["S"]}, {"1": [_rep("2026-09-08", "A", 100),
                                        {"dimensions": {"campaign_id": None}, "metrics": {}}]})
    rows, _ = gmv_max.fetch(c, ["1"], date(2026, 9, 8), date(2026, 9, 8))
    assert len(rows) == 1 and rows[0]["cost"] == Decimal("100")


def test_fetch_keeps_cost_as_decimal_never_float():
    c = FakeClient({"1": ["S"]}, {"1": [_rep("2026-09-08", "A", "126687.25")]})
    rows, _ = gmv_max.fetch(c, ["1"], date(2026, 9, 8), date(2026, 9, 8))
    assert rows[0]["cost"] == Decimal("126687.25") and isinstance(rows[0]["cost"], Decimal)


def test_fetch_names_campaigns_when_the_list_is_available():
    c = FakeClient({"1": ["S"]}, {"1": [_rep("2026-09-08", "A", 1)]},
                   names={"1": [{"campaign_id": "A", "campaign_name": "majority black"}]})
    rows, _ = gmv_max.fetch(c, ["1"], date(2026, 9, 8), date(2026, 9, 8))
    assert rows[0]["campaign"] == "majority black"


# --- the two sources must not fight over the same rows ------------------------------------------
def test_windsor_stands_down_once_the_ads_api_is_authorised(monkeypatch):
    """Both write the same ShopAdDay rows; left running they restate each other every hour."""
    from apps.worker import scheduler as S
    monkeypatch.setattr(S.settings, "windsor_api_key", "k")
    monkeypatch.setattr(S, "_tiktok_ads_ready", lambda: True)
    assert S.ads_windsor(MagicMock(), lambda s: NS(shop=SHOP)) == {
        "skipped": "superseded by the TikTok Ads API"}


def test_readiness_needs_a_token_with_advertisers_not_just_an_app_id(monkeypatch):
    """An app id alone writes nothing, so it must not stand Windsor down."""
    from apps.worker import scheduler as S

    class Store:
        def __init__(self, tok): self.tok = tok
        def load(self): return self.tok

    monkeypatch.setattr(S.settings, "tiktok_ads_app_id", "")
    assert S._tiktok_ads_ready() is False
    monkeypatch.setattr(S.settings, "tiktok_ads_app_id", "app")
    import src.integrations.tiktok_shop.auth as A
    monkeypatch.setattr(A, "TokenStore", lambda p: Store(None))
    assert S._tiktok_ads_ready() is False
    monkeypatch.setattr(A, "TokenStore", lambda p: Store({"access_token": "t", "advertiser_ids": []}))
    assert S._tiktok_ads_ready() is False
    monkeypatch.setattr(A, "TokenStore", lambda p: Store({"access_token": "t", "advertiser_ids": ["1"]}))
    assert S._tiktok_ads_ready() is True


def test_ads_tiktok_job_skips_until_authorised(monkeypatch):
    from apps.worker import scheduler as S
    monkeypatch.setattr(S.settings, "tiktok_ads_app_id", "")
    assert S.ads_tiktok(MagicMock(), lambda s: NS(shop=SHOP)) == {
        "skipped": "TIKTOK_ADS_APP_ID not configured"}


# --- campaigns tab -------------------------------------------------------------------------------
def test_campaign_spend_leaves_cpo_and_roi_undefined_without_orders():
    """A zero would read as "free"; the absence of orders is not a cost per order of nothing."""
    from src.domain.dashboard import loaders as L

    session = MagicMock()
    session.execute.return_value.all.return_value = [
        ("1872852148459778", "majority black", Decimal("1281169"), 35, Decimal("2292746"), NOW, True),
        ("1875228349709633", "LIVE GMV Max", Decimal("228549"), 0, Decimal("0"), NOW, False),
    ]
    rows = L.campaign_spend(session, 1, date(2026, 9, 2), date(2026, 9, 9))
    assert [r["name"] for r in rows] == ["majority black", "LIVE GMV Max"]   # sorted by spend
    assert rows[0]["cost_per_order"] == Decimal("36605") and rows[0]["reported_roi"] == Decimal("1.79")
    assert rows[1]["cost_per_order"] is None and rows[1]["reported_roi"] == Decimal("0")
    assert rows[1]["final"] is False


def test_campaign_spend_hides_a_campaign_that_did_nothing_in_the_period():
    from src.domain.dashboard import loaders as L

    session = MagicMock()
    session.execute.return_value.all.return_value = [
        ("A", "ran", Decimal("100"), 1, Decimal("300"), NOW, True),
        ("B", "idle", Decimal("0"), 0, Decimal("0"), NOW, True),
    ]
    assert [r["campaign_id"] for r in L.campaign_spend(session, 1, date(2026, 9, 2), date(2026, 9, 9))] == ["A"]


# --- product headroom ----------------------------------------------------------------------------
def test_headroom_is_a_ratio_because_one_cpo_target_cannot_serve_both_products():
    """A 19,000 single pair and a 75,000 five-pack have different break-even CPOs by construction."""
    from src.domain.dashboard.loaders import _verdict

    # kids: contribution 136,077 over 2 orders vs 50,514 spent -> room to pay much more per order
    assert _verdict(Decimal("136077"), Decimal("50514"), 2)["verdict"] == "scale"
    # flagship: 1,122,245 contribution against 1,263,330 spent -> every extra order is bought at a loss
    assert _verdict(Decimal("1122245"), Decimal("1263330"), 34)["verdict"] == "cut"
    assert _verdict(Decimal("1122245"), Decimal("1263330"), 34)["headroom"] == Decimal("0.89")


def test_spend_without_orders_is_called_out_not_scored():
    """No orders is not a headroom of zero; it is a product the money bought nothing from."""
    from src.domain.dashboard.loaders import _verdict
    assert _verdict(Decimal(0), Decimal("13368"), 0) == {"headroom": None, "verdict": "no_orders"}
    assert _verdict(Decimal(0), Decimal(0), 0)["verdict"] == "no_data"


def test_every_bridge_product_carries_a_verdict_even_with_no_sales():
    """The no-sales branch builds its row separately and used to omit the fields the UI reads."""
    from src.domain.dashboard import loaders as L

    session = MagicMock()
    session.execute.return_value.all.side_effect = [
        [(7, Decimal("13368"))],          # spend by product
        [],                                # product daily rows: none sold
        [],                                # videos
        [],                                # video-product links
    ]
    session.get.return_value = NS(external_product_id="X", title="Wanita Putih")
    out = L.creative_bridge(session, 1, date(2026, 9, 2), date(2026, 9, 9))
    row = out["products"][0]
    assert row["verdict"] == "no_orders" and row["headroom"] is None
    assert row["profit"] == Decimal("-13368")


def test_bridge_video_carries_its_reference_for_a_watch_link():
    """video_reference (the poster's handle) has to reach the dashboard, or a video can't be
    linked back to the real TikTok post."""
    from src.domain.dashboard import loaders as L

    session = MagicMock()
    session.execute.return_value.all.side_effect = [
        [],                                                          # spend by product
        [],                                                          # product daily rows
        [(9, "7685303303969852673", "Shop deals now", "user556272867", 500, 10, 2, Decimal("50000"))],
        [],                                                          # video-product links
    ]
    out = L.creative_bridge(session, 1, date(2026, 9, 2), date(2026, 9, 9))
    v = out["videos"][0]
    assert v["video_reference"] == "user556272867" and v["external_video_id"] == "7685303303969852673"
    assert v["gpm"] == Decimal("100000")


# --- deleted campaigns ---------------------------------------------------------------------------
def test_a_deleted_campaign_keeps_its_spend_in_the_day_total(monkeypatch):
    """TikTok drops a deleted campaign from the report, past days included. On 13 Sept 2026 that
    rewrote a closed day from 449,689 down to 224; the money was spent all the same."""
    calls = _capture(monkeypatch)
    seen = {}

    def absent(session, shop_id, day, present):
        seen["present"] = present
        return Decimal("449465")

    monkeypatch.setattr(T, "_absent_spend", absent)
    out = T.ingest(_session(), SHOP, [_row("2026-09-08", "LIVE", 224)], {}, now=NOW)
    assert calls[0]["cost"] == "449689" and out["written"] == 1
    assert seen["present"] == {"LIVE"}          # only campaigns missing from the report are added


def test_a_day_held_only_by_the_deleted_part_is_not_rewritten_every_run(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setattr(T, "_absent_spend", lambda *a: Decimal("449465"))
    monkeypatch.setattr(T, "_stored", lambda *a: NS(cost=Decimal("449689"), partial=False, manual=False))
    out = T.ingest(_session(), SHOP, [_row("2026-09-08", "LIVE", 224)], {}, now=NOW)
    assert out["unchanged"] == 1 and calls == []
