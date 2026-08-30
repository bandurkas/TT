from datetime import date
from decimal import Decimal

import pytest

from src.analytics.attribution import AttributionMethod, Confidence
from src.analytics.profitability import (
    AllocatedAds,
    CostVersion,
    CostVersionNotFoundError,
    CurrencyMismatchError,
    DuplicateTransactionError,
    FinanceTxn,
    InternalCosts,
    OrderItemInput,
    ProfitStatus,
    contribution_profit_before_ads,
    dedupe_transactions,
    duplicate_transaction_ids,
    estimated_net_profit,
    net_seller_revenue,
    order_profit,
    pick_cost_version,
    revenue_breakdown,
)
from src.analytics.transaction_types import NormalizedType

D = Decimal
IDR = "IDR"
ORDER_DATE = date(2026, 8, 15)


def txn(
    tid: str,
    native: str,
    amount: str | int,
    *,
    currency: str = IDR,
    item: str | None = None,
    settlement: str | None = None,
    payout: str | None = None,
    ntype: NormalizedType | None = None,
) -> FinanceTxn:
    return FinanceTxn(
        external_transaction_id=tid,
        native_type=native,
        amount=D(amount),
        currency=currency,
        normalized_type=ntype,
        order_item_id=item,
        settlement_id=settlement,
        payout_id=payout,
    )


def cost(sku: str = "LOMIRA-WHITE-5", **kw: object) -> CostVersion:
    base: dict[str, object] = {
        "sku_id": sku,
        "effective_from": date(2026, 8, 1),
        "effective_to": None,
        "cogs_per_unit": D(25000),
        "packaging_per_unit": D(1500),
        "currency": IDR,
    }
    base.update(kw)
    return CostVersion(**base)  # type: ignore[arg-type]


def item(iid: str = "i1", sku: str = "LOMIRA-WHITE-5", qty: int = 1, price: int = 75000):
    return OrderItemInput(
        order_item_id=iid, sku_id=sku, quantity=qty, unit_sale_price=D(price), currency=IDR
    )


ADS = AllocatedAds(D(12000), IDR, AttributionMethod.DIRECT_CREATIVE, Confidence.HIGH)

SPEC_TXNS = [
    txn("t1", "sale", 75000, settlement="s1"),
    txn("t2", "platform_commission", 8000, settlement="s1"),
    txn("t3", "affiliate_commission", 5000, settlement="s1"),
]


def test_spec_fixture_exact_23500() -> None:
    r = order_profit("o1", ORDER_DATE, [item()], SPEC_TXNS, [cost()], ADS)
    assert r.net_seller_revenue == D(62000)
    assert r.costs.cogs == D(25000)
    assert r.costs.packaging == D(1500)
    assert r.contribution_profit_before_ads == D(35500)
    assert r.allocated_ad_cost == D(12000)
    assert r.estimated_net_profit == D("23500")
    assert r.profit_status is ProfitStatus.SETTLED
    assert r.attribution_method is AttributionMethod.DIRECT_CREATIVE
    assert r.attribution_confidence is Confidence.HIGH


def test_pure_formulas() -> None:
    costs = InternalCosts(cogs=D(25000), packaging=D(1500))
    assert contribution_profit_before_ads(D(62000), costs) == D(35500)
    assert estimated_net_profit(D(35500), D(12000)) == D(23500)


def test_cogs_scales_with_quantity() -> None:
    r = order_profit("o", ORDER_DATE, [item(qty=3)], [txn("t", "sale", 225000)], [cost()])
    assert r.costs.cogs == D(75000)
    assert r.costs.packaging == D(4500)
    assert r.contribution_profit_before_ads == D(145500)


def test_tiktok_fee_reduces_revenue_regardless_of_sign() -> None:
    pos = net_seller_revenue([txn("a", "sale", 100), txn("b", "service_fee", 10)])
    neg = net_seller_revenue([txn("a", "sale", 100), txn("b", "service_fee", -10)])
    assert pos == neg == D(90)


def test_affiliate_commission() -> None:
    b = revenue_breakdown([txn("a", "sale", 100000), txn("b", "affiliate_commission", 7000)])
    assert b.affiliate_commission == D(7000)
    assert b.net_seller_revenue == D(93000)


def test_platform_subsidy_increases_revenue() -> None:
    b = revenue_breakdown([txn("a", "sale", 50000), txn("b", "platform_discount", 5000)])
    assert b.platform_subsidies == D(5000)
    assert b.net_seller_revenue == D(55000)


def test_seller_discount_reduces_revenue() -> None:
    b = revenue_breakdown([txn("a", "sale", 50000), txn("b", "seller_discount", 4000)])
    assert b.seller_discounts == D(4000)
    assert b.net_seller_revenue == D(46000)


def test_partial_refund() -> None:
    txns = SPEC_TXNS + [txn("r1", "refund", 20000, settlement="s1")]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.revenue.refunds == D(20000)
    assert r.estimated_net_profit == D(3500)
    assert r.profit_status is ProfitStatus.SETTLED


def test_refund_in_later_settlement_is_adjusted() -> None:
    txns = SPEC_TXNS + [txn("r1", "refund", 20000, settlement="s2")]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.estimated_net_profit == D(3500)
    assert r.profit_status is ProfitStatus.ADJUSTED
    # any REDUCES-type txn outside the sale's settlement: same rule
    txns = SPEC_TXNS + [txn("f9", "service_fee", 100, settlement="s3")]
    assert order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS).profit_status is (
        ProfitStatus.ADJUSTED
    )
    # PAID sale with a later refund: ADJUSTED beats PAID
    txns = [txn("t1", "sale", 75000, settlement="s1", payout="p1"),
            txn("r1", "refund", 1000, settlement="s2")]
    assert order_profit("o", ORDER_DATE, [item()], txns, [cost()]).profit_status is (
        ProfitStatus.ADJUSTED
    )


def test_full_refund_status() -> None:
    txns = SPEC_TXNS + [txn("r1", "refund", 75000, settlement="s1")]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.profit_status is ProfitStatus.REFUNDED
    assert r.net_seller_revenue == D(-13000)
    assert r.estimated_net_profit == D(-51500)


def test_settlement_adjustment_positive_sets_adjusted() -> None:
    txns = SPEC_TXNS + [txn("adj", "settlement_adjustment", 1000, settlement="s2")]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.revenue.adjustments == D(1000)
    assert r.estimated_net_profit == D(24500)
    assert r.profit_status is ProfitStatus.ADJUSTED


def test_negative_adjustment() -> None:
    txns = SPEC_TXNS + [txn("adj", "adjustment", -2000)]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.revenue.adjustments == D(-2000)
    assert r.estimated_net_profit == D(21500)
    assert r.profit_status is ProfitStatus.ADJUSTED


def test_adjustment_inside_same_settlement_is_not_post_settlement() -> None:
    txns = SPEC_TXNS + [txn("adj", "shipping_adjustment", -500, settlement="s1")]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.profit_status is ProfitStatus.SETTLED
    assert r.revenue.adjustments == D(-500)


def test_unsettled_fee_after_settled_sale_is_provisional() -> None:
    txns = SPEC_TXNS + [txn("f2", "service_fee", 1000)]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.profit_status is ProfitStatus.PROVISIONAL


def test_missing_settlement_is_provisional() -> None:
    txns = [txn("t1", "sale", 75000), txn("t2", "platform_commission", 8000)]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.profit_status is ProfitStatus.PROVISIONAL
    assert any("provisional" in w for w in r.warnings)


def test_no_sale_txn_yet_is_provisional() -> None:
    r = order_profit("o", ORDER_DATE, [item()], [], [cost()])
    assert r.profit_status is ProfitStatus.PROVISIONAL
    assert r.net_seller_revenue == D(0)
    assert r.estimated_net_profit == D(-26500)
    assert r.attribution_method is None


def test_paid_when_payout_present() -> None:
    txns = [txn("t1", "sale", 75000, settlement="s1", payout="p1")]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()])
    assert r.profit_status is ProfitStatus.PAID


def test_ad_cost_allocation_in_order() -> None:
    ads = AllocatedAds(D(4000), IDR, AttributionMethod.PROPORTIONAL, Confidence.MEDIUM)
    r = order_profit("o", ORDER_DATE, [item()], SPEC_TXNS, [cost()], ads)
    assert r.estimated_net_profit == D(31500)
    assert r.attribution_method is AttributionMethod.PROPORTIONAL
    assert r.attribution_confidence is Confidence.MEDIUM


def test_multiple_skus_split_reconciles() -> None:
    items = [item("i1", "A", qty=2, price=30000), item("i2", "B", qty=1, price=40000)]
    txns = [
        txn("s", "sale", 100000, settlement="s1"),
        txn("f", "platform_commission", 10001, settlement="s1"),
        txn("aff", "affiliate_commission", 3000, item="i2", settlement="s1"),
    ]
    versions = [
        cost("A", cogs_per_unit=D(10000), packaging_per_unit=D(500)),
        cost("B", cogs_per_unit=D(20000), packaging_per_unit=D(1000)),
    ]
    ads = AllocatedAds(D(7), IDR, AttributionMethod.PROPORTIONAL, Confidence.MEDIUM)
    r = order_profit("o", ORDER_DATE, items, txns, versions, ads)
    assert r.net_seller_revenue == D(86999)
    assert sum(i.net_seller_revenue for i in r.items) == r.net_seller_revenue
    assert sum(i.allocated_ad_cost for i in r.items) == D(7)
    assert sum(i.estimated_net_profit for i in r.items) == r.estimated_net_profit
    i1, i2 = r.items
    # order-level 89999 split 60/40 -> floor 53999.4 -> 53999, 35999.6 -> 35999, remainder 1 -> i1
    assert i1.net_seller_revenue == D(54000)
    assert i2.net_seller_revenue == D(35999) - D(3000)
    assert i1.allocated_ad_cost == D(5) and i2.allocated_ad_cost == D(2)
    assert i1.costs.cogs == D(20000) and i2.costs.cogs == D(20000)


def test_unknown_order_item_id_warns_and_allocates_order_level() -> None:
    items = [item("i1", "A", qty=1, price=60000), item("i2", "B", qty=1, price=40000)]
    txns = [txn("s", "sale", 100000, settlement="s1"),
            txn("f", "platform_commission", 10000, item="ghost", settlement="s1")]
    versions = [cost("A", cogs_per_unit=D(1)), cost("B", cogs_per_unit=D(1))]
    r = order_profit("o", ORDER_DATE, items, txns, versions)
    assert any("1 txns reference unknown order_item_id" in w for w in r.warnings)
    assert r.net_seller_revenue == D(90000)
    assert [i.net_seller_revenue for i in r.items] == [D(54000), D(36000)]


def test_informational_item_fields_do_not_affect_profit() -> None:
    it = OrderItemInput("i1", "LOMIRA-WHITE-5", 1, D(75000), IDR, discounts=D(5000))
    assert it.net_item_value == D(70000)
    r = order_profit("o1", ORDER_DATE, [it], SPEC_TXNS, [cost()], ADS)
    assert r.estimated_net_profit == D(23500)


def test_historical_cogs_version() -> None:
    versions = [
        cost(
            effective_from=date(2026, 7, 1), effective_to=date(2026, 8, 1), cogs_per_unit=D(20000)
        ),
        cost(effective_from=date(2026, 8, 1), effective_to=None, cogs_per_unit=D(25000)),
    ]
    assert pick_cost_version(versions, "LOMIRA-WHITE-5", date(2026, 7, 31)).cogs_per_unit == D(
        20000
    )
    assert pick_cost_version(versions, "LOMIRA-WHITE-5", date(2026, 8, 1)).cogs_per_unit == D(25000)
    old = order_profit("o", date(2026, 7, 15), [item()], SPEC_TXNS, versions, ADS)
    assert old.costs.cogs == D(20000)
    assert old.estimated_net_profit == D(28500)
    assert old.items[0].cost_version.effective_from == date(2026, 7, 1)


def test_cost_version_overlap_latest_wins_and_missing_raises() -> None:
    versions = [
        cost(effective_from=date(2026, 8, 1), cogs_per_unit=D(1)),
        cost(effective_from=date(2026, 8, 10), cogs_per_unit=D(2)),
    ]
    assert pick_cost_version(versions, "LOMIRA-WHITE-5", ORDER_DATE).cogs_per_unit == D(2)
    with pytest.raises(CostVersionNotFoundError):
        pick_cost_version(versions, "LOMIRA-WHITE-5", date(2026, 7, 1))
    with pytest.raises(CostVersionNotFoundError):
        pick_cost_version(versions, "OTHER", ORDER_DATE)


def test_duplicate_transaction_detection() -> None:
    txns = SPEC_TXNS + [txn("t2", "platform_commission", 8000, settlement="s1")]
    assert duplicate_transaction_ids(txns) == ["t2"]
    assert duplicate_transaction_ids(SPEC_TXNS) == []
    assert [t.external_transaction_id for t in dedupe_transactions(txns)] == ["t1", "t2", "t3"]
    with pytest.raises(DuplicateTransactionError):
        order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert order_profit(
        "o", ORDER_DATE, [item()], dedupe_transactions(txns), [cost()], ADS
    ).estimated_net_profit == D(23500)


def test_unknown_transactions_excluded_but_reported() -> None:
    txns = SPEC_TXNS + [txn("u", "MYSTERY_FEE", 999)]
    r = order_profit("o", ORDER_DATE, [item()], txns, [cost()], ADS)
    assert r.estimated_net_profit == D(23500)
    assert r.revenue.unknown_count == 1
    assert r.revenue.unknown_amount == D(999)
    assert any("UNKNOWN" in w for w in r.warnings)


def test_explicit_normalized_type_overrides_native() -> None:
    t = txn("x", "weird_native", 100, ntype=NormalizedType.SALE_PROCEEDS)
    assert t.ntype is NormalizedType.SALE_PROCEEDS
    assert net_seller_revenue([t]) == D(100)


def test_currency_precision_usd() -> None:
    usd_item = OrderItemInput("i1", "S", 3, D("19.99"), "USD")
    txns = [
        txn("s", "sale", "59.97", currency="USD", settlement="s1"),
        txn("f", "commission", "5.10", currency="USD", settlement="s1"),
    ]
    cv = CostVersion("S", date(2026, 8, 1), None, D("7.333"), "USD", packaging_per_unit=D("0.10"))
    ads = AllocatedAds(D("0.05"), "USD", AttributionMethod.BLENDED, Confidence.LOW)
    r = order_profit("o", ORDER_DATE, [usd_item], txns, [cv], ads)
    assert r.net_seller_revenue == D("54.87")
    assert r.costs.cogs == D("21.999")
    assert r.estimated_net_profit == D("32.521")
    assert r.estimated_net_profit == D("59.97") - D("5.10") - D("21.999") - D("0.30") - D("0.05")


def test_currency_mismatch_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        order_profit("o", ORDER_DATE, [item()], [txn("s", "sale", 1, currency="USD")], [cost()])
    with pytest.raises(CurrencyMismatchError):
        order_profit("o", ORDER_DATE, [item()], SPEC_TXNS, [cost(currency="USD")])
    with pytest.raises(CurrencyMismatchError):
        order_profit(
            "o",
            ORDER_DATE,
            [item()],
            SPEC_TXNS,
            [cost()],
            AllocatedAds(D(1), "USD", AttributionMethod.BLENDED, Confidence.LOW),
        )
    with pytest.raises(CurrencyMismatchError):
        order_profit(
            "o",
            ORDER_DATE,
            [item(), OrderItemInput("i2", "X", 1, D(1), "USD")],
            SPEC_TXNS,
            [cost()],
        )


def test_empty_items_rejected() -> None:
    with pytest.raises(ValueError):
        order_profit("o", ORDER_DATE, [], SPEC_TXNS, [cost()])
