import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.analytics.finance_fields import (
    EMITTED_ROLES,
    FIELD_MAP,
    RESIDUAL_FIELD,
    RESIDUAL_NOTE,
    FieldSpec,
    Role,
    StatementKind,
    amount,
    classify_statement,
    identity_holds,
    shipping_passthrough_net,
    statement_linkage,
    statement_record_to_txns,
)
from src.analytics.profitability import (
    CostVersion,
    OrderItemInput,
    ProfitStatus,
    net_seller_revenue,
    order_profit,
    revenue_breakdown,
)
from src.analytics.transaction_types import NormalizedType, revenue_effect

D = Decimal
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "tiktok_shop"
ADULT = "1736823576747934791"  # Dewasa 41-47
KIDS = "1736823576747869255"  # Remaja 36-40

# Seller Center income export, August 2026 ("Total settlement amount"); docs/reconciliation-2026-08.md
SELLER_CENTER = {
    "585649789132637561": ("81480", "91000", "-9520"),
    "585617420006360209": ("74928", "91000", "-16072"),
    "585615568104490414": ("88830", "100000", "-11170"),
    "585588423474579252": ("0", "0", "0"),
    "585625312034653821": ("81480", "91000", "-9520"),
    "585615511133325145": ("90060", "100000", "-9940"),
    "585598525834495045": ("89760", "100000", "-10240"),
    "585583340052055265": ("88830", "100000", "-11170"),
    "585579844588504809": ("83160", "100000", "-16840"),
    "585641188963484967": ("-10250", "0", "-10250"),
    "585583943233078299": ("89760", "100000", "-10240"),
    "585656874805134466": ("74655", "91000", "-16345"),
}
# "Dynamic commission" + "Order processing fee" per order in the export
EXPORT_RESIDUAL = {
    "585649789132637561": "-8530", "585617420006360209": "-8530", "585615568104490414": "-9250",
    "585588423474579252": "0", "585625312034653821": "-8530", "585615511133325145": "-9250",
    "585598525834495045": "-9250", "585583340052055265": "-9250", "585579844588504809": "-9250",
    "585641188963484967": "-8530", "585583943233078299": "-9250", "585656874805134466": "-8530",
}
AD_ROWS = ["-421800", "-444000", "-98235", "-98152", "-58846", "-1110000", "-64972", "-29353"]

COSTS = [
    CostVersion(ADULT, date(2026, 8, 1), None, D(25000), "IDR"),
    CostVersion(KIDS, date(2026, 8, 1), None, D(50000), "IDR"),
]


@pytest.fixture(scope="module")
def august() -> dict[str, list[dict]]:
    return json.loads((FIX / "august_statements.json").read_text())["orders"]


@pytest.fixture(scope="module")
def single() -> dict:
    d = json.loads((FIX / "order_statement_transactions_settled.json").read_text())
    return d["statement_transactions"][0]


def _record(august: dict, oid: str) -> dict:
    recs = august[oid]
    assert len(recs) == 1
    return recs[0]


def _items(record: dict) -> list[OrderItemInput]:
    return [
        OrderItemInput(
            order_item_id=s["sku_id"],
            sku_id=s["sku_id"],
            quantity=int(s["quantity"]),
            unit_sale_price=D(s["gross_sales_amount"]) / int(s["quantity"]),
            currency=s["currency"],
        )
        for s in record["sku_statement_transactions"]
    ]


# ---------- FIELD_MAP coverage / consistency


def test_field_map_covers_every_observed_field(august, single):
    observed: set[str] = set(single)
    for s in single["sku_statement_transactions"]:
        observed |= set(s)
    for recs in august.values():
        for r in recs:
            observed |= set(r)
            for s in r["sku_statement_transactions"]:
                observed |= set(s)
    assert observed <= FIELD_MAP.keys(), sorted(observed - FIELD_MAP.keys())


def test_field_map_roles_and_types():
    for name, spec in FIELD_MAP.items():
        assert isinstance(spec, FieldSpec)
        if spec.role in EMITTED_ROLES:
            assert spec.normalized is not None, name
    assert FIELD_MAP["gross_sales_amount"].normalized is NormalizedType.SALE_PROCEEDS
    assert FIELD_MAP["seller_discount_amount"].normalized is NormalizedType.SELLER_DISCOUNT
    assert FIELD_MAP["affiliate_commission_amount"].normalized is NormalizedType.AFFILIATE_COMMISSION
    assert FIELD_MAP["shipping_cost_amount"].normalized is NormalizedType.SHIPPING_FEE
    assert FIELD_MAP["adjustment_amount"].normalized is NormalizedType.OTHER_ADJUSTMENT
    assert FIELD_MAP["gross_sales_refund_amount"].normalized is NormalizedType.REFUND
    for f in ("pit_amount", "isr_income_tax_amount", "iva_vat_amount", "sales_tax_amount"):
        assert FIELD_MAP[f].normalized is NormalizedType.TAX
    for f in ("fee_amount", "revenue_amount", "settlement_amount"):
        assert FIELD_MAP[f].role is Role.AGGREGATE
    # platform discount is platform-funded and already inside gross: never emitted
    assert FIELD_MAP["platform_discount_amount"].normalized is NormalizedType.PLATFORM_SUBSIDY
    assert FIELD_MAP["platform_discount_amount"].role not in EMITTED_ROLES
    for f in (
        "customer_shipping_fee_amount",
        "shipping_fee_amount",
        "platform_shipping_fee_discount_amount",
        "actual_shipping_fee_amount",
    ):
        assert FIELD_MAP[f].role is Role.PASSTHROUGH


# ---------- data identities (verified on real August records)


def test_identity_and_revenue_composition(august):
    for oid, recs in august.items():
        r = recs[0]
        assert identity_holds(r), oid
        a = amount
        assert a(r, "revenue_amount") == (
            a(r, "gross_sales_amount")
            + a(r, "seller_discount_amount")
            + a(r, "gross_sales_refund_amount")
            + a(r, "seller_discount_refund_amount")
        ), oid
        assert a(r, "net_sales_amount") == a(r, "revenue_amount"), oid


def test_platform_discount_does_not_reduce_revenue(august):
    r = _record(august, "585617420006360209")
    assert amount(r, "platform_discount_amount") == D(-3640)
    assert amount(r, "gross_sales_amount") + amount(r, "seller_discount_amount") == D(91000)
    assert amount(r, "revenue_amount") == D(91000)


def test_shipping_passthrough_nets_to_zero(august, single):
    for oid, recs in august.items():
        assert shipping_passthrough_net(recs[0]) == 0, oid
        r = recs[0]
        assert amount(r, "shipping_fee_amount") == -(
            amount(r, "customer_shipping_fee_amount")
            + amount(r, "customer_paid_shipping_fee_refund_amount")
        ), oid
    assert shipping_passthrough_net(single) == 0


def test_residual_equals_export_dynamic_commission_plus_processing_fee(august):
    for oid, recs in august.items():
        txns = statement_record_to_txns(recs[0], oid)
        resid = sum((t.amount for t in txns if t.native_type == RESIDUAL_FIELD), D(0))
        assert resid == D(EXPORT_RESIDUAL[oid]), oid
        for t in txns:
            if t.native_type == RESIDUAL_FIELD:
                assert t.ntype is NormalizedType.PLATFORM_COMMISSION


# ---------- adapter -> engine


def test_net_seller_revenue_equals_settlement_all_orders(august):
    for oid, recs in august.items():
        r = recs[0]
        txns = statement_record_to_txns(r, oid)
        assert net_seller_revenue(txns) == amount(r, "settlement_amount"), oid
        assert len({t.external_transaction_id for t in txns}) == len(txns)
        assert all(t.settlement_id == r["statement_id"] for t in txns), oid
        assert not any(t.ntype is NormalizedType.UNKNOWN for t in txns), oid


def test_fee_components_sum_to_fee_amount(august):
    for oid, recs in august.items():
        r = recs[0]
        txns = statement_record_to_txns(r, oid)
        fee_types = {
            NormalizedType.PLATFORM_COMMISSION,
            NormalizedType.AFFILIATE_COMMISSION,
            NormalizedType.SHIPPING_FEE,
            NormalizedType.SERVICE_FEE,
            NormalizedType.TRANSACTION_FEE,
            NormalizedType.TAX,
        }
        fees = sum((revenue_effect(t.ntype, t.amount) for t in txns if t.ntype in fee_types), D(0))
        assert fees == amount(r, "fee_amount"), oid


def test_single_fixture_record(single):
    txns = statement_record_to_txns(single, "585489904998712566")
    assert net_seller_revenue(txns) == D(80482)
    b = revenue_breakdown(txns)
    assert b.affiliate_commission == D(7338)
    assert b.shipping == D(2930)
    assert b.platform_fees == D(19518 - 7338 - 2930)
    assert b.platform_subsidies == 0  # platform discount not emitted
    assert all(t.order_item_id == "1736823576747934791" for t in txns)


def test_per_sku_split_used_when_exact(august):
    r = _record(august, "585617420006360209")
    txns = statement_record_to_txns(r, "585617420006360209", sku_to_item={ADULT: "item-1"})
    assert {t.order_item_id for t in txns} == {"item-1"}
    assert all(t.external_transaction_id.startswith(f"{r['id']}:{ADULT}:") for t in txns)


def test_fallback_to_order_level_when_sku_rows_inexact(august):
    r = dict(_record(august, "585617420006360209"))
    bad = dict(r["sku_statement_transactions"][0])
    bad["settlement_amount"] = "1"
    r["sku_statement_transactions"] = [bad]
    txns = statement_record_to_txns(r, "x")
    assert all(t.order_item_id is None for t in txns)
    assert net_seller_revenue(txns) == amount(r, "settlement_amount")
    r["sku_statement_transactions"] = []
    assert all(t.order_item_id is None for t in statement_record_to_txns(r, "x"))


def test_unknown_field_warns_and_is_excluded(august, caplog):
    r = dict(_record(august, "585649789132637561"))
    r["sku_statement_transactions"] = []
    r["mystery_fee_amount"] = "-777"
    r["mystery_zero_amount"] = "0"
    r["mystery_text"] = "abc"
    with caplog.at_level(logging.WARNING, logger="src.analytics.finance_fields"):
        txns = statement_record_to_txns(r, "x")
    unknown = [t for t in txns if t.ntype is NormalizedType.UNKNOWN]
    assert [t.native_type for t in unknown] == ["mystery_fee_amount"]
    assert unknown[0].amount == D(-777)
    assert net_seller_revenue(txns) == amount(r, "settlement_amount")  # UNKNOWN excluded
    assert sum("mystery" in m for m in caplog.messages) == 3


def test_linkage_and_status(august):
    r = _record(august, "585649789132637561")
    link = statement_linkage(r)
    assert link.settled and link.statement_id == r["statement_id"]
    assert link.statement_time == 1787961600 and link.currency == "IDR"
    pending = dict(r, status="PENDING", sku_statement_transactions=[])
    txns = statement_record_to_txns(pending, "x")
    assert all(t.settlement_id is None for t in txns)
    p = order_profit("x", date(2026, 8, 21), _items(r), txns, COSTS)
    assert p.profit_status is ProfitStatus.PROVISIONAL
    paid = statement_record_to_txns(r, "x", payout_id="pay-1")
    p2 = order_profit("x", date(2026, 8, 21), _items(r), paid, COSTS)
    assert p2.profit_status is ProfitStatus.PAID


# ---------- statements list classification


@pytest.mark.parametrize("amt", AD_ROWS)
def test_classify_ad_deduction_api_shape(amt):
    stmt = {"revenue_amount": "0", "fee_amount": "0", "adjustment_amount": amt, "settlement_amount": amt}
    assert classify_statement(stmt) is StatementKind.AD_DEDUCTION


@pytest.mark.parametrize("amt", AD_ROWS[:6])
def test_classify_ad_deduction_export_rows(amt):
    row = {
        "Transaction type": "GMV payment for TikTok Ads",
        "Total settlement amount": amt,
        "Adjustment amount": amt,
    }
    assert classify_statement(row) is StatementKind.AD_DEDUCTION
    assert classify_statement({"Adjustment amount": amt}) is StatementKind.AD_DEDUCTION


def test_classify_order_and_other():
    assert (
        classify_statement({"revenue_amount": "91000", "fee_amount": "-9520", "adjustment_amount": "0"})
        is StatementKind.ORDER_SETTLEMENT
    )
    assert (
        classify_statement({"revenue_amount": "0", "fee_amount": "-10250", "adjustment_amount": "0"})
        is StatementKind.ORDER_SETTLEMENT
    )
    assert classify_statement({"revenue_amount": "0", "fee_amount": "0", "adjustment_amount": "2500"}) is (
        StatementKind.OTHER
    )
    assert classify_statement({}) is StatementKind.OTHER


# ---------- reconciliation vs Seller Center


def test_reconciliation_august_vs_seller_center(august, caplog):
    caplog.set_level(logging.INFO, logger="test_finance_fields")
    logger = logging.getLogger("test_finance_fields")
    rows = []
    total_settle = total_cogs = total_contrib = D(0)
    for oid, recs in august.items():
        r = recs[0]
        txns = statement_record_to_txns(r, oid)
        p = order_profit(oid, date(2026, 8, 20), _items(r), txns, COSTS)
        settle, revenue, fees = (D(x) for x in SELLER_CENTER[oid])
        assert p.net_seller_revenue == settle, oid
        assert p.net_seller_revenue == amount(r, "settlement_amount"), oid
        assert p.revenue.sale_proceeds - p.revenue.seller_discounts - p.revenue.refunds + (
            p.revenue.adjustments
        ) == revenue, oid
        assert -(p.revenue.platform_fees + p.revenue.affiliate_commission + p.revenue.shipping) == (
            fees
        ), oid
        assert sum((i.net_seller_revenue for i in p.items), D(0)) == p.net_seller_revenue
        expected_status = (
            ProfitStatus.REFUNDED if amount(r, "gross_sales_refund_amount") else ProfitStatus.SETTLED
        )
        assert p.profit_status is expected_status, oid
        rows.append((oid, p.net_seller_revenue, p.costs.cogs, p.contribution_profit_before_ads))
        total_settle += p.net_seller_revenue
        total_cogs += p.costs.cogs
        total_contrib += p.contribution_profit_before_ads
    logger.info("%-20s %12s %10s %14s", "order", "settlement", "cogs", "contrib_pre_ads")
    for oid, s, c, k in rows:
        logger.info("%-20s %12s %10s %14s", oid, s, c, k)
    logger.info("%-20s %12s %10s %14s", "TOTAL", total_settle, total_cogs, total_contrib)
    assert total_settle == D(832693)
    assert total_cogs == D(25000 * 9 + 50000 * 3)
    assert total_contrib == total_settle - total_cogs


# --- review fixes: mismatch / non-finite / id fallback / residual note -------------------
def test_mismatch_flagged_for_unknown_revenue_side_field(caplog):
    r = {"id": "t1", "statement_id": "s1", "status": "SETTLED", "currency": "IDR",
         "gross_sales_amount": "100", "fee_amount": "-10", "revenue_amount": "100",
         "adjustment_amount": "0", "settlement_amount": "95", "mystery_bonus_amount": "5"}
    with caplog.at_level(logging.ERROR):
        txns = statement_record_to_txns(r, "o1")
    assert txns.mismatch == D(5)
    assert any(t.native_type == "mystery_bonus_amount" and t.ntype is NormalizedType.UNKNOWN
               for t in txns)
    assert "delta 5" in caplog.text
    clean = {k: v for k, v in r.items() if k != "mystery_bonus_amount"}
    clean["settlement_amount"] = "90"
    assert statement_record_to_txns(clean, "o1").mismatch is None


def test_dec_rejects_non_finite():
    r = {"id": "t1", "gross_sales_amount": "NaN", "fee_amount": "Infinity",
         "settlement_amount": "0"}
    txns = statement_record_to_txns(r, "o1")
    assert txns == [] and txns.mismatch is None


def test_txn_id_fallback_includes_statement_id():
    a = {"statement_id": "s1", "status": "SETTLED", "gross_sales_amount": "10",
         "revenue_amount": "10", "settlement_amount": "10"}
    b = {**a, "statement_id": "s2"}
    ids = {t.external_transaction_id for t in statement_record_to_txns(a, "o1")} | \
        {t.external_transaction_id for t in statement_record_to_txns(b, "o1")}
    assert ids == {"o1:s1:gross_sales_amount", "o1:s2:gross_sales_amount"}
    assert statement_record_to_txns({"gross_sales_amount": "1", "settlement_amount": "1"}, "o9")[0] \
        .external_transaction_id == "o9:gross_sales_amount"


def test_residual_txn_carries_note():
    r = {"id": "t1", "fee_amount": "-7", "settlement_amount": "-7"}
    txns = statement_record_to_txns(r, "o1")
    assert [(t.native_type, t.note) for t in txns] == [(RESIDUAL_FIELD, RESIDUAL_NOTE)]
