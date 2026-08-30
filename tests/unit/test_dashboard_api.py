from datetime import UTC, date, datetime
from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from apps.api import dashboard as A
from apps.api.main import app
from src.domain.dashboard import compute as C

SHOP = NS(id=1, name="Lomira", currency="IDR", timezone="Asia/Jakarta")
CFG = NS(minimum_net_margin=D("0.10"), minimum_sample_orders=5, minimum_sample_impressions=1000,
         minimum_sample_clicks=30)


def _row(d):
    return NS(ad_cost_known=True, profit_inputs_known=True, ad_cost_partial=False, metric_date=d, orders=1, units=1, gmv=D(100000), net_seller_revenue=D(91000), fees=D(9000),
              affiliate=D(0), cogs=D(25000), contribution=D(66000), ad_cost=D(20000), net_profit=D(46000),
              refunds=D(0), settled_orders=1, provisional_orders=0)


def client():
    session = MagicMock()
    app.dependency_overrides[A.get_session] = lambda: session
    return TestClient(app), session


def patches():
    return [patch.object(A, "advertising_summary", lambda s, sid, a, b, tz: {"cost": D(20000)*sum(a <= date(2026, 8, k) <= b for k in range(1, 6)), "known_cost": D(20000)*sum(a <= date(2026, 8, k) <= b for k in range(1, 6)), "partial_days": [], "gmv_pay": D(20000), "status": "reported"}),
            patch.object(A.L, "shop_and_config", lambda s, sid: (SHOP, CFG)),
            patch.object(A.L, "today_local", lambda shop: date(2026, 8, 31)),
            patch.object(A.L, "shop_daily", lambda s, sid, a, b: [_row(date(2026, 8, k)) for k in range(1, 6)
                                                                  if a <= date(2026, 8, k) <= b]),
            patch.object(A.L, "shop_funnel_by_day", lambda s, sid, a, b: {date(2026, 8, 1): (1000, 50, 3)}),
            patch.object(A.L, "current_profits", lambda s, sid, a, b, tz: ([], {}, {})),
            patch.object(A.L, "last_sync", lambda s, sid: (datetime(2026, 8, 31, tzinfo=UTC), 12)),
            patch.object(A.L, "cogs_gaps", lambda s, sid, a, b, tz: (0, 0)),
            patch.object(A.L, "ad_deductions", lambda s, sid, a, b, tz: [{"date": date(2026, 8, 3), "settlement_id": "x",
                                                                           "amount": D(20000)}]),
            patch.object(A.L, "videos_with_metrics", lambda s, sid, a, b: ({}, {})),
            patch.object(A.L, "shop_metrics", lambda s, sid, a, b: []),
            patch.object(A.L, "product_daily", lambda s, sid, a, b: []),
            patch.object(A.L, "product_funnel", lambda s, sid, a, b: {}),
            patch.object(A.L, "products", lambda s, sid: {}),
            patch.object(A.L, "video_product_metrics", lambda s, sid, a, b: []),
            patch.object(A.L, "funnel_counts", lambda s, sid, p, tz: C.FunnelCounts(1000, 50, 3, 5, 5, 5))]


def with_patches(fn):
    def run():
        ps = patches()
        for p in ps:
            p.start()
        try:
            return fn()
        finally:
            for p in ps:
                p.stop()
            app.dependency_overrides.clear()
    return run


@with_patches
def _overview():
    c, _ = client()
    return c.get("/api/dashboard/overview?from=2026-08-01&to=2026-08-31").json()


def test_overview_shape_and_period():
    body = _overview()
    assert body["period"] == {"start": "2026-08-01", "end": "2026-08-31"}
    assert body["compare"] == {"start": "2026-07-01", "end": "2026-07-31"}
    cards = {c["key"]: c for c in body["cards"]}
    assert cards["net_profit"]["value"] == "230000" and cards["orders"]["value"] == "5"
    assert cards["gmv"]["sparkline"][-1] == "0" and cards["net_margin"]["value"] == "0.5055"
    assert cards["reported_roas"]["value"] is None
    assert body["health"]["components"]["data_quality"] == body["data_quality"]["score"]
    assert any("BLENDED" in n for n in body["notes"]) and body["shop"]["currency"] == "IDR"


@with_patches
def _others():
    c, _ = client()
    return {p: c.get(p).json() for p in ("/api/dashboard/trends?from=2026-08-01&to=2026-08-05",
                                          "/api/analytics/products", "/api/analytics/videos",
                                          "/api/analytics/campaigns", "/api/analytics/creators",
                                          "/api/analytics/video-products",
                                          "/api/dashboard/funnel", "/api/dashboard/insights")}


def test_other_endpoints():
    out = _others()
    tr = out["/api/dashboard/trends?from=2026-08-01&to=2026-08-05"]
    assert len(tr["series"]) == 5 and tr["series"][-1]["cum_net_profit"] == "230000"
    assert tr["events"][0]["type"] == "ad_deduction"
    assert out["/api/analytics/products"]["rows"] == []
    assert out["/api/analytics/videos"]["cards"] == [] and "NOT_AVAILABLE" in out["/api/analytics/videos"]["ad_spend_note"]
    camp = out["/api/analytics/campaigns"]
    assert camp["available"] is False and camp["shop_level_ad_cost"] == "100000" and camp["advertising"]["gmv_pay"] == "20000"
    assert out["/api/analytics/creators"]["rows"][0]["creator"].startswith("Affiliate")
    f = out["/api/dashboard/funnel"]
    assert f["stages"][0]["count"] == 1000 and f["waterfall"]["orders"] == 0
    vp = out["/api/analytics/video-products"]
    assert vp["shop_split"]["gmv_total"] == "0" and vp["dependency"]["best_lag"] is None and vp["products"] == []
    ins = out["/api/dashboard/insights"]
    assert isinstance(ins["findings"], list) and "opportunities" in ins and "risks" in ins


def test_tasks_create_patch_list():
    c, session = client()
    stored = {}

    def add(t):
        t.id, t.created_at, t.updated_at = 7, datetime(2026, 8, 31, tzinfo=UTC), datetime(2026, 8, 31, tzinfo=UTC)
        stored["t"] = t
    session.add.side_effect = add
    session.get.side_effect = lambda model, i: stored.get("t") if i == 7 else None
    with patch.object(A.L, "shop_and_config", lambda s, sid: (SHOP, CFG)):
        r = c.post("/api/tasks", json={"title": "Review GMV Max budget", "team": "performance", "priority": "P1",
                                       "detail": "why", "deadline": "2026-09-01", "impact_note": "+Rp 600k/mo",
                                       "evidence": {"insight": "ads_below_break_even"}})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["id"] == 7 and body["status"] == "today" and body["deadline"] == "2026-09-01"
        assert body["evidence"] == {"insight": "ads_below_break_even"} and body["source"] == "manual"
        assert body["impact_note"] == "+Rp 600k/mo"
        r = c.patch("/api/tasks/7", json={"status": "done", "result_note": "budget capped"})
        assert r.json()["status"] == "done" and r.json()["done_at"] and r.json()["result_note"] == "budget capped"
        r = c.patch("/api/tasks/7", json={"status": "review"})
        assert r.json()["done_at"] is None
        assert c.patch("/api/tasks/99", json={"status": "done"}).status_code == 404
        assert c.post("/api/tasks", json={"title": "x", "team": "nope"}).status_code == 422
        session.scalars.return_value = [stored["t"]]
        lst = c.get("/api/tasks").json()
        assert lst["columns"]["review"][0]["id"] == 7 and lst["tasks"][0]["title"] == "Review GMV Max budget"
    app.dependency_overrides.clear()
