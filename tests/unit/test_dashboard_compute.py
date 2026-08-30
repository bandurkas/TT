from datetime import UTC, date, datetime
from decimal import Decimal as D
from types import SimpleNamespace as NS

from src.analytics.creative_scoring import ScoringConfig
from src.analytics.data_quality import DataQuality, DQState
from src.domain.dashboard import compute as C
from src.domain.dashboard import insights as I

AUG = C.Period(date(2026, 8, 1), date(2026, 8, 31))


def day(d, orders=1, gmv=100000, net=91000, fees=9000, cogs=25000, ads=20000, refunds=0, settled=1, prov=0):
    net_profit = D(net) - D(cogs) - D(ads)
    return NS(metric_date=d, orders=orders, units=orders, gmv=D(gmv), net_seller_revenue=D(net), fees=D(fees),
              affiliate=D(0), cogs=D(cogs), contribution=D(net) - D(cogs), ad_cost=D(ads),
              net_profit=net_profit, refunds=D(refunds), settled_orders=settled, provisional_orders=prov)


def test_periods_default_and_previous():
    cur, cmp = C.default_periods(date(2026, 8, 31))
    assert (cur.start, cur.end) == (date(2026, 8, 1), date(2026, 8, 31))
    assert (cmp.start, cmp.end) == (date(2026, 7, 1), date(2026, 7, 31)) and cmp.days == 31
    cur, cmp = C.default_periods(date(2026, 8, 31), date(2026, 8, 20), date(2026, 8, 10))
    assert cur.start == date(2026, 8, 10) and cur.end == date(2026, 8, 20)


def test_sum_daily_totals_and_ratios():
    rows = [day(date(2026, 8, 1)), day(date(2026, 8, 2), orders=2, gmv=200000, net=182000, prov=1, settled=1),
            day(date(2026, 7, 31))]
    t = C.sum_daily(rows, AUG, funnel={date(2026, 8, 1): (1000, 30, 2), date(2026, 8, 2): (1000, 20, 1)},
                    refunded={date(2026, 8, 2): 1})
    assert t.orders == 3 and t.gmv == D(300000) and t.days_with_data == 2
    assert t.clicks == 50 and t.impressions == 2000 and t.refunded_orders == 1 and t.video_orders == 3
    assert t.cvr == D("0.06") and t.ctr == D("0.025") and t.refund_rate == D("0.3333")
    assert t.aov == D(100000) and t.settlement_coverage == D("0.6667")
    assert t.blended_roas == D("6.82") and t.break_even_roas == D("1.22")
    assert t.net_margin == (t.net_profit / t.net_seller_revenue).quantize(D("0.0001"))


def test_kpi_change_and_status():
    k = C.kpi("net_profit", D(120), D(100), [D(1), D(2)], status=C._status(D(120), "up"))
    assert k["change_abs"] == D(20) and k["change_pct"] == D("0.2") and k["status"] == "good"
    assert C.pct_change(D(5), D(0)) is None and C.pct_change(D(50), D(-100)) == D("1.5")
    assert C._status(D("0.05"), "up", D("0.10")) == "bad" and C._status(D("0.05"), "down", D("0.10")) == "good"
    assert C._status(None, "up") == "neutral"


def test_business_health_cards_and_score():
    rows = [day(date(2026, 8, k)) for k in range(1, 11)]
    cur = C.sum_daily(rows, AUG, funnel={date(2026, 8, 1): (1000, 50, 5)})
    prev = C.sum_daily([day(date(2026, 7, k), ads=60000) for k in range(1, 11)], AUG.previous(),
                       funnel={date(2026, 7, 1): (1000, 50, 5)})
    dq = DataQuality(DQState.OK, 96, ())
    z = C.business_health(cur, prev, rows, AUG, D("0.10"), dq)
    cards = {c["key"]: c for c in z["cards"]}
    assert cards["net_profit"]["value"] == D(460000) and cards["net_profit"]["prev"] == D(60000)
    assert cards["reported_roas"]["value"] is None and "NOT_AVAILABLE" in cards["reported_roas"]["note"]
    assert len(cards["gmv"]["sparkline"]) == 7
    assert C.sparkline(rows, date(2026, 8, 10), "gmv")[-1] == D(100000)
    assert cards["ad_spend"]["provisional"] is True
    h = z["health"]
    assert set(h["components"]) == {"margin", "ad_efficiency", "conversion", "refunds", "data_quality"}
    assert h["components"]["data_quality"] == 96 and h["components"]["refunds"] == 100
    assert 0 <= h["score"] <= 100 and h["grade"] in ("GOOD", "FAIR", "POOR")
    u = z["unit_economics"]
    assert u["units"] == 10 and u["cogs_per_unit"] == D(25000) and u["net_per_unit"] == D(46000)


def test_trend_series_fills_gaps_and_cumulates():
    p = C.Period(date(2026, 8, 1), date(2026, 8, 3))
    s = C.trend_series([day(date(2026, 8, 1)), day(date(2026, 8, 3), ads=100000)], p)
    assert [x["net_profit"] for x in s] == [D(46000), D(0), D(-34000)]
    assert [x["cum_net_profit"] for x in s] == [D(46000), D(46000), D(12000)]
    assert s[1]["orders"] == 0


def test_product_rows_status_rules():
    def prow(pid, d, **kw):
        r = day(d, **kw)
        r.product_id = pid
        return r
    rows = [prow(1, date(2026, 8, k)) for k in range(1, 8)] + [prow(2, date(2026, 8, 1), ads=90000)] + \
           [prow(3, date(2026, 8, k), ads=0) for k in range(1, 6)]
    meta = {1: NS(title="A", external_product_id="x1"), 3: NS(title="C", external_product_id="x3")}
    out = C.product_rows(rows, meta, AUG, {(1, date(2026, 8, 1)): (1000, 100, 1)}, D("0.10"), 5)
    by = {r["product_id"]: r for r in out}
    assert by[1]["status"] == "HEALTHY" and by[1]["cvr"] is None and by[1]["title"] == "A"  # product CVR N/A
    assert by[2]["status"] == "SMALL_SAMPLE" and by[2]["title"] == "product 2"
    assert by[3]["status"] == "HEALTHY" and by[3]["ad_cost"] == D(0)
    big = [prow(5, date(2026, 8, k), ads=0) for k in range(1, 12)]
    assert C.product_rows(big, {}, AUG, {}, D("0.10"), 5)[0]["status"] == "SCALE"
    assert out[0]["net_profit"] >= out[-1]["net_profit"]
    loss = C.product_status(C.Totals(orders=6, net_seller_revenue=D(100), net_profit=D(-5)), D("0.1"), 5)
    assert loss[0] == "REDUCE"
    low = C.product_status(C.Totals(orders=6, net_seller_revenue=D(100), net_profit=D(5)), D("0.1"), 5)
    assert low[0] == "INVESTIGATE"


def test_video_cards_classification_and_sorting():
    def vm(d, imp, clk, orders, gmv, views, ctr=None):
        return NS(metric_date=d, impressions=imp, product_clicks=clk, orders=orders, gmv=D(gmv), views=views,
                  ctr=ctr)
    daily = {1: [vm(date(2026, 8, 20), 5000, 150, 6, 480000, 6000)],
             2: [vm(date(2026, 8, 20), 5000, 40, 0, 0, 5000)],
             3: [vm(date(2026, 8, 20), 100, 1, 0, 0, 120)],
             4: [vm(date(2026, 7, 1), 9000, 90, 1, 80000, 9000)]}
    meta = {i: NS(external_video_id=f"v{i}", caption="c", published_at=datetime(2026, 8, 10, tzinfo=UTC),
                  duration_seconds=15) for i in daily}
    cards = C.video_cards(daily, meta, AUG, date(2026, 8, 31), ScoringConfig(minimum_sample_impressions=1000))
    ids = [c["video_id"] for c in cards]
    assert 4 not in ids and ids[0] == 1
    by = {c["video_id"]: c for c in cards}
    assert by[1]["classification"] in ("WINNER", "PROMISING", "NEUTRAL") and by[1]["gpm"] == D(80000)
    assert by[3]["classification"] == "INSUFFICIENT_DATA"
    assert by[1]["ad_spend"] is None and "NOT_AVAILABLE" in by[1]["ad_spend_note"]
    assert by[1]["age_days"] == 21
    derived = C.video_cards({9: [vm(date(2026, 8, 20), None, 0, 2, 100000, 4000, D("0.025"))]},
                            {9: NS(external_video_id="v9", caption=None, published_at=None, duration_seconds=None)},
                            AUG, date(2026, 8, 31), ScoringConfig(minimum_sample_impressions=1000))[0]
    assert derived["impressions"] == 4000 and derived["clicks"] == 100 and derived["ctr"] == D("0.025")


def test_normalize_decimals():
    out = C.normalize({"a": D("25000.000000"), "b": [D("0E-6"), D("-1.50")], "c": {"d": D("0.1156")}, "e": 1})
    assert out == {"a": "25000", "b": ["0", "-1.5"], "c": {"d": "0.1156"}, "e": 1}


def test_funnel_view_and_waterfall():
    cur = C.FunnelCounts(10000, 100, 5, 50, 45, 30)
    base = C.FunnelCounts(10000, 200, 10, 40, 40, 40)
    f = C.funnel_view(cur, base, D(50000))
    assert f["stages"][0]["name"] == "video_view" and f["stages"][0]["count"] == 10000
    assert f["steps"][0]["rate"] == D("0.01") and f["steps"][0]["baseline_rate"] == D("0.02")
    assert f["pipeline"]["stages"][0]["count"] == 50 and f["pipeline"]["steps"][-1]["timing_only"] is True
    assert f["diagnosis"]["stage_from"] == "video_view" and f["diagnosis"]["estimated"] is True
    assert f["diagnosis"]["delta_pct"] == D("-0.5")
    lag = C.funnel_view(C.FunnelCounts(1000, 100, 50, 60, 55, 10), C.FunnelCounts(1000, 100, 50, 60, 55, 55),
                        D(1))
    assert lag["diagnosis"] is None  # settlement lag is not a deterioration
    pipe = C.funnel_view(C.FunnelCounts(10, 1, 0, 60, 40, 10), C.FunnelCounts(10, 1, 0, 60, 60, 60), D(1))
    assert pipe["diagnosis"]["stage_from"] == "order" and pipe["diagnosis"]["stage_to"] == "completed"
    profits = [NS(profit_status="SETTLED", sale_proceeds=D(100000), seller_discounts=D(9000), refunds=D(0),
                  platform_fees=D(8000), affiliate_commission=D(2000), seller_shipping=D(500), taxes=D(0),
                  subsidies=D(0), adjustments=D(0), cogs=D(25000), packaging=D(0), inbound_logistics=D(0),
                  other_variable=D(0), contribution_profit=D(55500), allocated_ad_cost=D(20000),
                  estimated_net_profit=D(35500), net_seller_revenue=D(80500))]
    w = C.waterfall(profits)
    steps = {s["key"]: s for s in w["steps"]}
    assert steps["revenue_after_seller_discounts"]["amount"] == D(91000)
    assert steps["tiktok_fees"]["amount"] == D(-8500) and steps["cogs"]["amount"] == D(-25000)
    assert steps["ad_deductions_blended"]["measured"] is False and steps["net_profit"]["amount"] == D(35500)
    assert w["orders"] == 1 and w["provisional_orders"] == 0


def test_insights_rules():
    cur = C.Totals(orders=30, units=30, gmv=D(3000000), net_seller_revenue=D(2400000), fees=D(300000),
                   cogs=D(750000), contribution=D(1650000), ad_cost=D(2230000), net_profit=D(-580000),
                   refunds=D(391000), refunded_orders=4, clicks=57, impressions=6972, settled_orders=30)
    prev = C.Totals(orders=20, net_seller_revenue=D(1000000), net_profit=D(100000), clicks=100, impressions=7000,
                    video_orders=5)
    prods = [{"product_id": 9, "title": "Abu", "status": "REDUCE", "status_reason": "net loss", "net_profit": D(-104000),
              "orders": 6}]
    vids = [{"video_id": 1, "external_video_id": "v1", "classification": "PROMISING", "confidence": "LOW",
             "ctr": D("0.0165"), "orders": 1, "gmv": D(80000), "reasons": ["ctr above median"], "clicks": 19},
            {"video_id": 2, "external_video_id": "v2", "classification": "TRAFFIC_NO_SALES", "confidence": "MEDIUM",
             "ctr": D("0.0095"), "orders": 0, "gmv": D(0), "reasons": ["no orders"], "clicks": 18}]
    funnel = {"diagnosis": {"stage_from": "impression", "stage_to": "click", "current_rate": D("0.0082"),
                            "baseline_rate": D("0.014"), "delta_pct": D("-0.41"), "evidence": ["e"],
                            "lost_profit": D(-240000)}}
    out = I.findings(cur, prev, D("0.10"), prods, vids, funnel, 5)
    keys = [f["key"] for f in out]
    assert keys[0] == "ads_below_break_even" and out[0]["severity"] == "CRITICAL" and out[0]["confidence"] == "LOW"
    assert "refund_rate_high" in keys and "funnel_deterioration" in keys and "product_loss:9" in keys
    assert next(f for f in out if f["key"] == "profit_vs_previous")["title"].startswith("Net profit -680.0%")
    assert next(f for f in out if f["key"] == "refund_rate_high")["title"].startswith("Refund rate 13.3%")
    assert "video_promising:1" in keys and "video_traffic_no_sales:2" in keys and "profit_vs_previous" in keys
    assert all("impact" in f and "source" in f and "measured" in f for f in out)
    ok = I.findings(C.Totals(orders=10, net_seller_revenue=D(1000), contribution=D(600), ad_cost=D(100),
                             net_profit=D(500)), C.Totals(), D("0.1"), [], [], {}, 5)
    assert ok[0]["key"] == "ads_above_break_even" and ok[0]["kind"] == "opportunity"


def test_data_quality_wrapper():
    cur = C.Totals(orders=10, settled_orders=9, provisional_orders=1)
    dq = C.data_quality(30, cur, 0, 0)
    assert dq.state in (DQState.OK, DQState.PARTIAL) and dq.score > 50
    assert C.data_quality(None, C.Totals(), 0, 0).score <= 100


def test_pearson_and_lag_dependency():
    days = [{"date": date(2026, 8, k), "video_views": 100 * k, "gmv_product_card": D(1000 * (k + 1))}
            for k in range(1, 11)]
    dep = C.lag_dependency(days)
    assert dep["lags"][0]["correlation"] == D(1) and dep["lags"][1]["n"] == 9 and dep["best_lag"] == 0
    assert C.pearson([D(1)] * 8, [D(k) for k in range(8)]) is None and C.pearson([D(1)], [D(2)]) is None
    flat = C.lag_dependency([{"date": date(2026, 8, k), "video_views": 5, "gmv_product_card": D(7)} for k in range(1, 9)])
    assert flat["best_lag"] is None


def test_video_product_map():
    def r(vid, pid, d, imp, clk, units, gmv):
        return NS(video_id=vid, product_id=pid, metric_date=d, impressions=imp, clicks=clk, units_sold=units,
                  gmv=D(gmv), customers=1)
    vpm = [r(1, 3, date(2026, 8, 5), 400, 10, 2, 180000), r(1, 3, date(2026, 8, 6), 81, 7, 1, 95700),
           r(2, 3, date(2026, 8, 7), 300, 5, 2, 178097), r(2, 4, date(2026, 8, 7), 38, 0, 0, 0),
           r(9, 3, date(2026, 7, 1), 999, 99, 9, 999)]
    prows = [{"product_id": 3, "title": "Pria Hitam", "external_product_id": "x3", "gmv": D(6468528), "orders": 68,
              "net_profit": D(1), "status": "SCALE"}]
    pmeta = {4: NS(title="Abu", external_product_id="x4")}
    vmeta = {1: NS(external_video_id="v1", caption="a"), 2: NS(external_video_id="v2", caption="b")}
    products, videos = C.video_product_map(vpm, prows, pmeta, vmeta, {1: 14884, 2: 2079}, {1: "PROMISING"}, AUG)
    p3 = products[0]
    assert p3["product_id"] == 3 and p3["video_gmv"] == D(453797) and p3["video_units"] == 5
    assert p3["video_share"] == D("0.0702") and p3["video_impressions"] == 781 and p3["video_clicks"] == 22
    assert p3["videos"][0]["external_video_id"] == "v1" and p3["videos"][0]["ctr"] == D("0.0353")
    p4 = next(p for p in products if p["product_id"] == 4)
    assert p4["status"] == "NO_SALES" and p4["video_share"] is None and p4["title"] == "Abu"
    assert videos[0]["video_id"] == 1 and videos[0]["views"] == 14884 and videos[0]["classification"] == "PROMISING"
    assert videos[1]["products"][0]["title"] == "Pria Hitam" and len(videos[1]["products"]) == 2


def test_video_history_lift_and_phase():
    def r(vid, pid, d, imp, clk, units, gmv):
        return NS(video_id=vid, product_id=pid, metric_date=d, impressions=imp, clicks=clk, units_sold=units,
                  gmv=D(gmv), customers=1)
    pub = datetime(2026, 8, 10, tzinfo=UTC)
    pdr = []
    for k in range(1, 25):
        d = date(2026, 8, k)
        o = 1 if k < 10 else 3
        pdr.append(NS(product_id=3, metric_date=d, gmv=D(100000 * o), orders=o, net_profit=D(40000 * o)))
    vpm = [r(1, 3, date(2026, 8, 10 + i), 100, 5, 1, 90000) for i in range(5)]
    vd = {1: [NS(metric_date=date(2026, 8, 10 + i), views=[500, 800, 300, 100, 50][i], impressions=100,
                 product_clicks=5, orders=1, gmv=D(90000)) for i in range(5)]}
    out = C.video_history(vpm, pdr, vd, {1: NS(external_video_id="v1", caption="c", published_at=pub)},
                          {3: NS(title="Pria")}, AUG, 5)
    p = out["products"][0]
    assert p["title"] == "Pria" and len(p["days"]) == 31 and p["days"][9]["video_gmv"] == D(90000)
    assert p["days"][9]["non_video_gmv"] == D(210000) and p["events"] == [
        {"date": date(2026, 8, 10), "video_id": 1, "external_video_id": "v1", "type": "published"}]
    lift = p["lifts"][0]
    assert lift["before"]["orders"] == 7 and lift["after"]["orders"] == 21 and lift["lift_pct"] == D(2)
    assert lift["verdict"] == "positive" and lift["after"]["video_gmv"] == D(450000)
    v = out["videos"][0]
    assert v["peak_day"] == date(2026, 8, 11) and v["peak_views"] == 800 and v["phase"] == "fading"
    assert v["recent_vs_peak"] == D("0.1875")
    pend = C.video_history(vpm, pdr, vd, {1: NS(external_video_id="v1", caption="c", published_at=pub)},
                           {3: NS(title="Pria")}, AUG, 5, data_end=date(2026, 8, 12))
    assert pend["products"][0]["lifts"][0]["verdict"] == "pending"
    assert C._lift_verdict(D(0), D(0), 0, 5) == ("insufficient", None)
    assert C._lift_verdict(D(1), D("0.5"), 4, 5) == ("negative", D("-0.5"))
