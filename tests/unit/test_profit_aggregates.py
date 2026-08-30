from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS

from src.domain.profit.aggregates import DailyAgg, product_daily, shop_daily

D = Decimal


def profit(oid, status="SETTLED", net=D(80482), cogs=D(25000), ads=D(0), fees=D(8518), aff=D(2000),
           refunds=D(0), items=None, pid=1):
    contrib = net - cogs
    items = items if items is not None else [
        {"product_id": 77, "quantity": 1, "gross_item_value": "100000", "net_seller_revenue": str(net),
         "cogs": str(cogs), "allocated_ad_cost": str(ads), "estimated_net_profit": str(contrib - ads)}]
    return NS(id=pid, order_id=oid, profit_status=status, sale_proceeds=D(100000), platform_fees=fees,
              seller_shipping=D(0), taxes=D(0), affiliate_commission=aff, refunds=refunds,
              net_seller_revenue=net, cogs=cogs, packaging=D(0), inbound_logistics=D(0),
              other_variable=D(0), contribution_profit=contrib, allocated_ad_cost=ads,
              estimated_net_profit=contrib - ads, inputs_snapshot={"items": items})


D18, D19 = date(2026, 8, 18), date(2026, 8, 19)


def test_shop_daily_math():
    ps = [profit(1, ads=D(30000)), profit(2, ads=D(20000), pid=2),
          profit(3, status="PROVISIONAL", net=D(80000), pid=3),
          profit(4, status="REFUNDED", net=D(-10250), cogs=D(0), fees=D(10250), refunds=D(100000), pid=4)]
    dates = {1: D18, 2: D18, 3: D19, 4: D19}
    agg = shop_daily(ps, dates)
    a18, a19 = agg[D18], agg[D19]
    assert a18.orders == 2 and a18.units == 2 and a18.settled_orders == 2 and a18.provisional_orders == 0
    assert a18.net_seller_revenue == D(160964) and a18.cogs == D(50000) and a18.ad_cost == D(50000)
    assert a18.contribution == D(110964) and a18.net_profit == D(60964)
    assert a18.fees == D(17036) and a18.affiliate == D(4000) and a18.gmv == D(200000)
    assert a18.net_margin == (D(60964) / D(160964)).quantize(D("0.000001"))
    assert a19.orders == 2 and a19.provisional_orders == 1 and a19.settled_orders == 1
    assert a19.refunds == D(100000) and a19.net_seller_revenue == D(69750)
    assert DailyAgg().net_margin is None and shop_daily(ps, {})== {}


def test_as_row_gmv_override_from_shop_metrics():
    a = shop_daily([profit(1)], {1: D18})[D18]
    row = a.as_row(None, gmv_override=D(123))
    assert row["gmv"] == D(123) and row["net_profit"] == D(55482) and row["orders"] == 1
    assert a.as_row(None)["gmv"] == D(100000)


def test_product_daily_splits_multi_product_order():
    items = [{"product_id": 77, "quantity": 1, "gross_item_value": "75000", "net_seller_revenue": "60000",
              "cogs": "25000", "allocated_ad_cost": "9000", "estimated_net_profit": "26000"},
             {"product_id": 88, "quantity": 2, "gross_item_value": "25000", "net_seller_revenue": "20000",
              "cogs": "10000", "allocated_ad_cost": "3000", "estimated_net_profit": "7000"}]
    p = profit(1, net=D(80000), cogs=D(35000), ads=D(12000), fees=D(8000), aff=D(4000), items=items)
    out = product_daily([p, profit(2, pid=2)], {1: D18, 2: D18})
    a77, a88 = out[(77, D18)], out[(88, D18)]
    assert a77.orders == 2 and a77.units == 2 and a88.orders == 1 and a88.units == 2
    assert a77.net_seller_revenue == D(60000) + D(80482) and a88.net_seller_revenue == D(20000)
    assert a77.ad_cost == D(9000) and a88.ad_cost == D(3000)
    assert a88.net_profit == D(7000) and a77.net_profit == D(26000) + D(55482)
    assert a88.fees == D(2000) and a88.affiliate == D(1000)  # 25% share of order-level fees
    assert a77.fees == D(6000) + D(8518)
    assert a77.contribution + a88.contribution == D(80000) - D(35000) + D(55482)
