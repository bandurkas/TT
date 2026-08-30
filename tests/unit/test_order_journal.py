from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from src.domain.dashboard import orders as O

NOW = datetime(2026, 8, 22, 10, tzinfo=UTC)


def sample():
    order = NS(id=1, external_order_id="DEMO-001", order_created_at=NOW,
               order_status="COMPLETED", currency="IDR")
    values = {k: D(0) for k in O.FIELDS}
    values.update(sale_proceeds=D(100000), seller_discounts=D(10000), platform_fees=D(9000),
                  affiliate_commission=D(2000), seller_shipping=D(1000), taxes=D(500),
                  refunds=D(10000), subsidies=D(1000), adjustments=D(-300), net_seller_revenue=D(68200),
                  cogs=D(25000), packaging=D(1500), inbound_logistics=D(500),
                  contribution_profit=D(41200), allocated_ad_cost=D(12000), estimated_net_profit=D(29200))
    txns = [("sale:gross_sales_amount", "SALE_PROCEEDS", "100000", "statement-A"),
            ("sale:seller_discount_amount", "SELLER_DISCOUNT", "-10000", "statement-A"),
            ("sale:fee_residual", "PLATFORM_COMMISSION", "-9000", "statement-A"),
            ("sale:affiliate_commission_amount", "AFFILIATE_COMMISSION", "-2000", "statement-A"),
            ("sale:shipping_cost_amount", "SHIPPING_FEE", "-1000", "statement-A"),
            ("sale:pit_amount", "TAX", "-500", "statement-A"),
            ("return:gross_sales_refund_amount", "REFUND", "-10000", "statement-B"),
            ("return:subsidy", "PLATFORM_SUBSIDY", "1000", "statement-B"),
            ("return:adjustment_amount", "OTHER_ADJUSTMENT", "-300", "statement-B")]
    profit = NS(**values, profit_status="ADJUSTED", currency="IDR", version=3,
                calculated_at=NOW, attribution_method="BLENDED", attribution_confidence="LOW",
                inputs_snapshot={"source": "settled", "txns": txns, "ad_window_days": 7,
                                 "cost_versions": [("SKU-A", "2026-08-01", "12500")]})
    records = [NS(statement_id="statement-A", settlement_amount=D(77500), currency="IDR",
                  statement_time=NOW, fetched_at=NOW, status="SETTLED"),
               NS(statement_id="statement-B", settlement_amount=D(-9300), currency="IDR",
                  statement_time=NOW, fetched_at=NOW, status="SETTLED")]
    return order, profit, records


def test_exact_waterfall_and_common_percentage_basis():
    order, profit, records = sample()
    out = O.breakdown(order, profit, [], records)
    lines = {r["key"]: r for r in out["lines"]}
    assert out["revenue_base"] == D(90000)
    assert lines["platform_fees"]["share"] == D("-0.100000")
    assert lines["estimated_net_profit"]["amount"] == D(29200)
    assert lines["estimated_net_profit"]["share"] == D("0.324444")
    assert sum(r["amount"] for r in out["lines"] if not r["subtotal"]) == D(29200)
    assert out["calculation_check"]["status"] == out["settlement_check"]["status"] == "matched"
    assert out["settlement_check"]["actual"] == D(68200)
    assert out["cost_versions"][0]["cogs_per_unit"] == D(12500)
    assert lines["allocated_ad_cost"]["evidence"] == lines["estimated_net_profit"]["evidence"] == "estimate"
    assert out["transactions"][2]["field"] == "fee_residual"
    assert sum(t["amount"] for t in out["transactions"]) == D(68200)


@pytest.mark.parametrize("base", [D(0), D(-100)])
def test_nonpositive_base_never_produces_misleading_percentages(base):
    order, profit, records = sample()
    profit.seller_discounts = profit.sale_proceeds - base
    out = O.breakdown(order, profit, [], records)
    assert all(r["share"] is None for r in out["lines"])
    assert out["amounts"]["profit_share"] is None


def test_missing_profit_is_not_zero():
    order, _, _ = sample()
    out = O.breakdown(order, None, [], [])
    assert out["amounts"] is None and out["lines"] == []
    assert out["state"] == "not_calculated" and out["calculation_check"] is None


@pytest.mark.parametrize("source,status,expected", [("settled", "SETTLED", "final"),
    ("settled", "FUTURE", "preliminary"), ("unsettled_record", "REFUNDED", "preliminary"),
    ("ratio_estimate", "PROVISIONAL", "preliminary"), ("unknown", "PAID", "preliminary")])
def test_final_status_requires_final_source(source, status, expected):
    _, p, _ = sample()
    p.inputs_snapshot["source"], p.profit_status = source, status
    assert O.financial_state(p) == expected


def test_unknown_fees_and_cogs_are_not_confirmed_zero():
    order, profit, records = sample()
    profit.inputs_snapshot.update(source="ratio_estimate", fee_ratio=None, cogs_missing=True, txns=[])
    out = O.breakdown(order, profit, [], records)
    assert "fees_unknown_zero_assumption" in out["warnings"]
    assert "cogs_missing" in out["warnings"]
    lines = {r["key"]: r for r in out["lines"]}
    assert lines["platform_fees"]["evidence"] == lines["taxes"]["evidence"] == "unavailable"
    assert lines["cogs"]["evidence"] == "unavailable"
    assert out["settlement_check"]["status"] == "pending"


@pytest.mark.parametrize("change", ["missing", "currency", "unsettled", "empty_amount"])
def test_settlement_reconciliation_fails_closed(change):
    order, profit, records = sample()
    if change == "missing":
        records.pop()
    elif change == "currency":
        records[0].currency = "USD"
    elif change == "unsettled":
        records[0].status = "UNSETTLED"
    else:
        records[0].settlement_amount = None
    assert O.breakdown(order, profit, [], records)["settlement_check"]["status"] == "unavailable"


def test_only_snapshot_linked_statements_are_reconciled():
    order, profit, records = sample()
    unrelated = deepcopy(records[0])
    unrelated.statement_id, unrelated.settlement_amount = "future-revision", D(999999)
    out = O.breakdown(order, profit, [], records + [unrelated])
    assert len(out["settlements"]) == 2 and out["settlement_check"]["difference"] == 0


def test_source_and_arithmetic_checks_are_independent():
    order, profit, records = sample()
    profit.estimated_net_profit += D("0.000001")
    out = O.breakdown(order, profit, [], records)
    assert out["calculation_check"]["status"] == "mismatch"
    assert out["calculation_check"]["differences"]["estimated_net_profit"] == D("-0.000001")
    assert out["settlement_check"]["status"] == "matched"
    records[0].settlement_amount += D(1)
    assert O.breakdown(order, profit, [], records)["settlement_check"]["difference"] == D(-1)


def test_output_whitelists_fields_instead_of_leaking_raw_data():
    order, profit, records = sample()
    order.buyer_email = "must-not-leak"
    profit.inputs_snapshot["warnings"] = ["private source payload"]
    records[0].raw_response_id = 999
    out = repr(O.breakdown(order, profit, [], records))
    assert "must-not-leak" not in out and "private source payload" not in out and "raw_response_id" not in out


@pytest.mark.parametrize("kind", ["UNKNOWN", "FUTURE_TRANSACTION"])
def test_unknown_transactions_remain_visible_without_being_double_counted(kind):
    order, profit, records = sample()
    profit.inputs_snapshot["txns"].append(("sale:new_fee", kind, "-123.45", "statement-A"))
    out = O.breakdown(order, profit, [], records)
    tx = out["transactions"][-1]
    assert tx["group"] == "unknown" and tx["raw_amount"] == D("-123.45")
    assert tx["amount"] == 0 and "unknown_transactions" in out["warnings"]
    assert out["settlement_check"]["status"] == "matched"
    assert out["amounts"]["net_profit"] == D(29200)
