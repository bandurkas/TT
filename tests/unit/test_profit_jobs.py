"""Profit job: txn building from ORM-like records, versioning, blended ad allocation, provisional."""
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace as NS

from src.analytics.profitability import CostVersion, ProfitStatus
from src.domain.profit import jobs
from src.domain.profit.jobs import (
    OrderCtx,
    ProfitInputs,
    ad_deductions_by_day,
    allocate_ads_blended,
    build_txns,
    compute_from_inputs,
    estimate_provisional,
    persist_order_profits,
    record_to_dict,
    trailing_fee_ratio,
)

D = Decimal
TZ = "Asia/Jakarta"
ORDER_EXT = "585489904998712566"
SKU_EXT = "1737179740638708807"
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def jkt(y, m, d, h=10):  # shop-local time -> UTC-aware
    return datetime(y, m, d, h - 7, tzinfo=UTC)


def record(order_ext=ORDER_EXT, rid=1, status="SETTLED", st=jkt(2026, 8, 20), **over):
    amounts = {"gross_sales_amount": D(100000), "seller_discount_amount": D(-9000),
               "revenue_amount": D(91000), "net_sales_amount": D(91000),
               "fee_amount": D(-10518), "affiliate_commission_amount": D(-2000),
               "shipping_cost_amount": D(-1250), "platform_commission_amount": D(0),
               "adjustment_amount": D(0), "settlement_amount": D(80482),
               "actual_shipping_fee_amount": D(-12000), "customer_shipping_fee_amount": D(12000)}
    amounts.update(over)
    return NS(id=rid, shop_id=1, external_order_id=order_ext, external_transaction_id=f"txn{rid}",
              statement_id=f"stmt{rid}", statement_time=st, order_create_time=jkt(2026, 8, 18),
              status=status, currency="IDR", **amounts)


def sku_record(rid=1, qty=1, **over):
    r = record(rid=rid, **over)
    return NS(id=rid * 10, record_id=rid, external_sku_id=SKU_EXT, sku_name="s", product_name="p",
              quantity=qty, currency="IDR",
              **{k: getattr(r, k) for k in vars(r) if k.endswith("_amount")})


def order(oid=1, ext=ORDER_EXT, created=jkt(2026, 8, 18), status="COMPLETED", gmv=D(91000)):
    return NS(id=oid, shop_id=1, external_order_id=ext, order_created_at=created, order_status=status,
              currency="IDR", gross_merchandise_value=gmv, seller_discount=D(0), buyer_paid_amount=gmv)


def item(iid=11, oid=1, sku_id=5, qty=1, price=D(100000)):
    return NS(id=iid, order_id=oid, sku_id=sku_id, quantity=qty, unit_sale_price=price,
              gross_item_value=price * qty)


COST = [CostVersion(SKU_EXT, date(2026, 1, 1), None, D(25000), "IDR")]
SKU_MAP = {5: SKU_EXT}
PROD_MAP = {SKU_EXT: 77}


def ctx(o, items=None, rec=None, skus=None):
    return OrderCtx(order=o, items=items if items is not None else [item(oid=o.id)], record=rec,
                    sku_records=skus or [], sku_external_by_id=SKU_MAP, product_by_sku_ext=PROD_MAP)


def inputs(orders, settlements=(), cost=COST, fee_records=None, default_cogs=None):
    return ProfitInputs(shop_id=1, currency="IDR", timezone=TZ, orders=orders, cost_versions=list(cost),
                        settlements=list(settlements),
                        fee_ratio_records=[c.record for c in orders if c.record] if fee_records is None
                        else fee_records, default_cogs=default_cogs)


# --- txn building ----------------------------------------------------------------------------
def test_record_to_dict_shapes_api_payload():
    d = record_to_dict(record(), [sku_record()])
    assert d["id"] == "txn1" and d["statement_id"] == "stmt1" and d["status"] == "SETTLED"
    assert d["statement_time"] == int(jkt(2026, 8, 20).timestamp())
    assert d["settlement_amount"] == "80482" and "platform_commission_amount" in d
    assert d["sku_statement_transactions"][0]["sku_id"] == SKU_EXT
    assert d["sku_statement_transactions"][0]["settlement_amount"] == "80482"


def test_build_txns_from_orm_record_matches_settlement():
    c = ctx(order(), rec=record(), skus=[sku_record()])
    txns, warns = build_txns(c)
    assert warns == []
    from src.analytics.profitability import net_seller_revenue
    assert net_seller_revenue(txns) == D(80482)
    assert all(t.settlement_id == "stmt1" for t in txns)
    assert {t.order_item_id for t in txns} == {"11"}  # sku -> order item id
    assert any(t.native_type == "fee_residual" and t.amount == D(-7268) for t in txns)


def test_settled_order_profit_reconciliation_fixture():
    res = compute_from_inputs(inputs([ctx(order(), rec=record(), skus=[sku_record()])]), NOW)
    p = res[0].profit
    assert p.net_seller_revenue == D(80482) and p.costs.cogs == D(25000)
    assert p.contribution_profit_before_ads == D(55482) and p.allocated_ad_cost == 0
    assert p.profit_status is ProfitStatus.SETTLED and not res[0].is_estimate
    assert res[0].local_date == date(2026, 8, 18)
    assert res[0].items[0]["product_id"] == 77 and res[0].items[0]["quantity"] == 1


def test_missing_cogs_flagged_not_raised():
    res = compute_from_inputs(inputs([ctx(order(), rec=record())], cost=[]), NOW)
    p = res[0]
    assert p.profit.costs.cogs == 0 and p.snapshot["cogs_missing"] is True
    assert any(w.startswith("COGS missing") for w in p.profit.warnings)


def test_missing_cogs_uses_shop_default_when_set():
    res = compute_from_inputs(inputs([ctx(order(), items=[], rec=record(), skus=[sku_record(qty=2)])],
                                     cost=[], default_cogs=D(25000)), NOW)
    p = res[0]
    assert p.profit.costs.cogs == D(50000)
    assert p.snapshot["cogs_missing"] is True and p.snapshot["cogs_default_used"] is True
    assert any("shop default 25000" in w for w in p.profit.warnings)
    assert p.snapshot["cost_versions"] == [(SKU_EXT, "1970-01-01", "25000")]


def test_known_cogs_not_overridden_by_default():
    res = compute_from_inputs(inputs([ctx(order(), rec=record())], default_cogs=D(1)), NOW)
    assert res[0].profit.costs.cogs == D(25000) and res[0].snapshot["cogs_default_used"] is False


def test_items_fallback_to_sku_records_when_no_order_items():
    res = compute_from_inputs(inputs([ctx(order(), items=[], rec=record(), skus=[sku_record(qty=2)])]), NOW)
    assert res[0].profit.costs.cogs == D(50000) and res[0].profit.items[0].quantity == 2


# --- versioning ------------------------------------------------------------------------------
class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


def test_persist_inserts_v1_then_noop_then_v2():
    s = FakeSession()
    calcs = compute_from_inputs(inputs([ctx(order(), rec=record())]), NOW)
    st = persist_order_profits(s, calcs, {}, NOW)
    assert st == {"inserted": 1, "unchanged": 0}
    row = s.added[0]
    assert row.version == 1 and row.is_current and row.net_seller_revenue == D(80482)
    assert row.attribution_method == "BLENDED" and row.attribution_confidence == "LOW"
    assert row.inputs_snapshot["hash"] == calcs[0].hash

    st2 = persist_order_profits(s, calcs, {1: row}, NOW)
    assert st2 == {"inserted": 0, "unchanged": 1} and row.is_current and len(s.added) == 1

    changed = compute_from_inputs(inputs([ctx(order(), rec=record(adjustment_amount=D(-1000),
                                                                settlement_amount=D(79482)))]), NOW)
    assert changed[0].hash != calcs[0].hash
    st3 = persist_order_profits(s, changed, {1: row}, NOW)
    assert st3["inserted"] == 1 and row.is_current is False
    assert s.added[1].version == 2 and s.added[1].net_seller_revenue == D(79482)


# --- ad deductions / blended allocation --------------------------------------------------------
def settlement(sid, at, net, gross=D(0), extra=None):
    return NS(external_settlement_id=sid, settlement_at=at, gross_amount=gross, net_amount=net,
              extra=extra)


def test_ad_deductions_by_local_day():
    sets = [settlement("a", datetime(2026, 8, 22, 18, 0, tzinfo=UTC), D(-1110000)),  # 23rd JKT
            settlement("b", jkt(2026, 8, 27), D(-444000)),
            settlement("c", jkt(2026, 8, 27), D(-98235)),
            settlement("d", jkt(2026, 8, 27), D(80482), gross=D(91000)),  # order settlement
            settlement("e", jkt(2026, 8, 29), D(-421800), gross=D(0),
                       extra={"classification": "AD_DEDUCTION"}),
            settlement("f", jkt(2026, 8, 29), D(-2500), gross=D(0),
                       extra={"classification": "OTHER"})]
    by_day = ad_deductions_by_day(sets, TZ)
    assert by_day == {date(2026, 8, 23): D(1110000), date(2026, 8, 27): D(542235),
                      date(2026, 8, 29): D(421800)}


def test_blended_allocation_lumpy_deduction_sums_to_total():
    spend = {date(2026, 8, 23): D(1110000), date(2026, 8, 27): D(542235)}
    orders = {"o1": (date(2026, 8, 17), D(80482)),   # in 23rd window only
              "o2": (date(2026, 8, 21), D(80482)),   # both windows
              "o3": (date(2026, 8, 25), D(-10250)),  # negative -> 0
              "o4": (date(2026, 8, 27), D(90060)),   # 27th window only
              "o5": (date(2026, 8, 28), D(88830))}   # after both -> 0
    alloc, unallocated, warns = allocate_ads_blended(spend, orders, "IDR")
    assert sum(alloc.values()) + unallocated == D(1652235)
    assert unallocated == 0 and not warns
    assert alloc["o3"] == 0 and alloc["o5"] == 0
    assert alloc["o1"] == D(555000) and alloc["o2"] > alloc["o1"] and alloc["o4"] > 0
    assert all(v == v.to_integral_value() for v in alloc.values())  # IDR quantum


def test_blended_allocation_no_orders_in_window_is_unallocated():
    alloc, unallocated, warns = allocate_ads_blended({date(2026, 8, 1): D(5000)},
                                                     {"o1": (date(2026, 8, 20), D(1000))}, "IDR")
    assert alloc == {"o1": D(0)} and unallocated == D(5000) and warns


def test_compute_allocates_deductions_across_orders():
    o1, o2 = order(1, "A", created=jkt(2026, 8, 18)), order(2, "B", created=jkt(2026, 8, 22))
    sets = [settlement("ad", jkt(2026, 8, 23), D(-100000))]
    res = compute_from_inputs(inputs([ctx(o1, rec=record("A", 1)), ctx(o2, rec=record("B", 2))], sets), NOW)
    ads = {r.external_order_id: r.profit.allocated_ad_cost for r in res}
    assert sum(ads.values()) == D(100000) and ads == {"A": D(50000), "B": D(50000)}
    assert res[0].profit.estimated_net_profit == D(55482) - D(50000)
    assert res[0].snapshot["ad_method"] == "BLENDED" and res[0].snapshot["ad_window_days"] == 7


# --- provisional estimate ---------------------------------------------------------------------
def test_trailing_fee_ratio():
    recs = [record(rid=1, st=jkt(2026, 8, 20)), record(rid=2, st=jkt(2026, 6, 1)),
            record(rid=3, status="PROCESSING")]
    assert trailing_fee_ratio(recs, date(2026, 8, 30), TZ) == (D(10518) / D(91000)).quantize(D("0.000001"))
    assert trailing_fee_ratio([], date(2026, 8, 30), TZ) is None


def test_estimate_provisional_is_labelled():
    o = order(gmv=D(91000))
    txns, warns = estimate_provisional(o, [], D("0.115582"), "IDR")
    assert warns[0] == jobs.PROVISIONAL_LABEL
    assert all(t.settlement_id is None for t in txns)
    fees = [t for t in txns if t.native_type == "platform_commission"]
    assert fees and fees[0].amount == D(10518)
    txns0, warns0 = estimate_provisional(o, [], None, "IDR")
    assert len(txns0) == 1 and "estimated fees = 0" in warns0[1]


def test_compute_provisional_order_status_and_snapshot():
    settled = ctx(order(1, "A"), rec=record("A", 1))
    pending = ctx(order(2, "B", created=jkt(2026, 8, 28)))
    cancelled = ctx(order(3, "C", status="CANCELLED"))
    res = compute_from_inputs(inputs([settled, pending, cancelled]), NOW)
    assert [r.external_order_id for r in res] == ["A", "B"]
    b = res[1]
    assert b.is_estimate and b.profit.profit_status is ProfitStatus.PROVISIONAL
    assert b.profit.warnings[0] == jobs.PROVISIONAL_LABEL and b.snapshot["estimate"] is True
    assert b.profit.net_seller_revenue == D(91000) - D(10518)
    assert b.snapshot["fee_ratio"] == "0.1156" and res[0].snapshot["fee_ratio"] is None


# --- review fixes (2026-08-31) ----------------------------------------------------------------
def _ctx_multi(o, recs, skus_by_rec=None):
    c = ctx(o, rec=recs[-1], skus=(skus_by_rec or {}).get(recs[-1].id, []))
    c.records = list(recs)
    c.sku_records_by_record = {r.id: (skus_by_rec or {}).get(r.id, []) for r in recs}
    return c


def test_since_allocation_consistent_with_full_run():
    o1, o2 = order(1, "A", created=jkt(2026, 8, 18)), order(2, "B", created=jkt(2026, 8, 22))
    sets = [settlement("ad1", jkt(2026, 8, 19), D(-40000)), settlement("ad2", jkt(2026, 8, 23), D(-100000))]
    orders = [ctx(o1, rec=record("A", 1)), ctx(o2, rec=record("B", 2))]
    full = {r.external_order_id: r.profit.allocated_ad_cost
            for r in compute_from_inputs(inputs(orders, sets), NOW)}
    inc = inputs(orders, sets)
    inc.since = date(2026, 8, 20)
    res = compute_from_inputs(inc, NOW)
    assert [r.external_order_id for r in res] == ["B"]  # look-back order A not persisted
    assert res[0].profit.allocated_ad_cost == full["B"] == D(50000)
    assert full["A"] == D(90000)


def test_multiple_settled_records_all_used_and_flagged():
    r1 = record(rid=1)
    zero = {k: D(0) for k in vars(r1) if k.endswith("_amount")}
    r2 = record(rid=2, st=jkt(2026, 8, 25), **{**zero, "adjustment_amount": D(-5000),
                                                "settlement_amount": D(-5000)})
    res = compute_from_inputs(inputs([_ctx_multi(order(), [r1, r2])]), NOW)
    p = res[0]
    assert p.profit.net_seller_revenue == D(75482)
    assert p.profit.profit_status is ProfitStatus.ADJUSTED
    assert {t.settlement_id for t in txns_of(p)} == {"stmt1", "stmt2"}
    assert any("2 settled statements" in w for w in p.profit.warnings)


def txns_of(calc):
    return [NS(settlement_id=t[3]) for t in calc.snapshot["txns"]]


def test_mismatch_surfaced_in_warnings_and_snapshot():
    r = record(settlement_amount=D(80487))  # identity broken -> emitted txns != settlement_amount
    res = compute_from_inputs(inputs([ctx(order(), rec=r)]), NOW)
    p = res[0]
    assert p.snapshot["mismatch"] and "MISMATCH" in p.snapshot["mismatch"][0]
    assert any(w.startswith("MISMATCH") for w in p.profit.warnings)
    clean = compute_from_inputs(inputs([ctx(order(), rec=record())]), NOW)[0]
    assert clean.snapshot["mismatch"] is None and clean.hash != p.hash


def test_unsettled_placeholder_record_used_for_provisional():
    ph = record(rid=9, status="PROCESSING", st=None)
    ph.statement_id = ""
    c = ctx(order())
    c.placeholder = ph
    res = compute_from_inputs(inputs([c], fee_records=[]), NOW)
    p = res[0]
    assert p.is_estimate and p.snapshot["source"] == "unsettled_record"
    assert p.profit.profit_status is ProfitStatus.PROVISIONAL
    assert p.profit.net_seller_revenue == D(80482)
    assert all(t[3] is None for t in p.snapshot["txns"])
    ph.revenue_amount = D(0)
    res0 = compute_from_inputs(inputs([c], fee_records=[]), NOW)
    assert res0[0].snapshot["source"] == "ratio_estimate"


def test_engine_error_isolated_per_order():
    bad_rec = record("B", 2)
    bad_rec.currency = "USD"
    bad = ctx(order(2, "B"), rec=bad_rec)
    errs: list[str] = []
    res = compute_from_inputs(inputs([ctx(order(1, "A"), rec=record("A", 1)), bad]), NOW, errs)
    assert [r.external_order_id for r in res] == ["A"]
    assert len(errs) == 1 and "B" in errs[0]


def test_hash_ignores_warning_text_and_decimal_exponent():
    a = compute_from_inputs(inputs([ctx(order(), rec=record())]), NOW)[0]
    b = compute_from_inputs(inputs([ctx(order(), rec=record(settlement_amount=D("80482.000000"),
                                                            gross_sales_amount=D("100000.00")))]), NOW)[0]
    assert a.hash == b.hash
    snap = dict(a.snapshot)
    snap["warnings"] = ["different wording"]
    assert jobs.snapshot_hash(snap) == a.hash
    assert jobs._ds(D("25000.000000")) == "25000" and jobs._ds(D("0E-6")) == "0"


def test_trailing_fee_ratio_skips_refunded_and_undated():
    good = record(rid=1, st=jkt(2026, 8, 20))
    refunded = record(rid=2, st=jkt(2026, 8, 21), revenue_amount=D(0), fee_amount=D(-5000))
    undated = record(rid=3, st=None)
    assert trailing_fee_ratio([good, refunded, undated], date(2026, 8, 30), TZ) == \
        (D(10518) / D(91000)).quantize(D("0.000001"))


def test_ad_credit_logged_not_netted(caplog):
    import logging
    sets = [settlement("ad", jkt(2026, 8, 23), D(-100000)), settlement("cr", jkt(2026, 8, 24), D(30000))]
    with caplog.at_level(logging.INFO, logger="tt.profit"):
        out = jobs.ad_deductions_by_day(sets, TZ)
    assert out == {date(2026, 8, 23): D(100000)}
    assert "CREDIT statement cr" in caplog.text and "ad deduction counted: ad" in caplog.text
