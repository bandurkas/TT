import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.dialects import postgresql

from src.db.models import Order, Settlement
from src.db.models_finance import STATEMENT_AMOUNT_FIELDS, OrderStatementRecord, ShopMetric
from src.domain.ingest import mappers as m
from src.domain.ingest.upserts import build_upsert

FX = Path(__file__).parents[1] / "fixtures" / "tiktok_shop"
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def load(name):
    return json.loads((FX / name).read_text())


def test_dec_ts_helpers():
    assert m.dec("100000") == Decimal(100000) and m.dec({"amount": "1.5"}) == Decimal("1.5")
    assert m.dec(None) is None and m.dec("") is None and m.dec("abc") is None
    assert m.dec(0.1) == Decimal("0.1")
    assert m.ts(1786780800) == datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    assert m.ts(1786780800000) == m.ts(1786780800) and m.ts(None) is None and m.ts("0") is None
    assert m.cur({"amount": "1", "currency": "IDR"}) == "IDR" and m.cur("1", "X") == "X"


def test_statement_record_mapping_all_fields_decimal():
    d = load("order_statement_transactions_settled.json")
    rec = d["statement_transactions"][0]
    row = m.map_order_statement_record(rec, shop_id=1, external_order_id=d["order_id"],
                                       order_create_time=d["order_create_time"],
                                       raw_response_id=7, fetched_at=NOW)
    assert row["statement_id"] == "7676544904109082376" and row["status"] == "SETTLED"
    assert row["external_transaction_id"] == "7672624939999987473"
    assert row["statement_time"] == datetime.fromtimestamp(1787356800, UTC)
    assert row["order_create_time"] == datetime.fromtimestamp(1786780800, UTC)
    for f in STATEMENT_AMOUNT_FIELDS:
        assert isinstance(row[f], Decimal), f
    assert row["settlement_amount"] == row["revenue_amount"] + row["fee_amount"] + row["adjustment_amount"]
    assert row["fee_amount"] == Decimal(-19518) and row["raw_response_id"] == 7
    # every amount key in the API record is captured by the model
    api_amounts = {k for k in rec if k.endswith("_amount") or k == "affiliate_commission_before_pit"}
    assert api_amounts <= set(STATEMENT_AMOUNT_FIELDS)
    assert set(row) <= {c.name for c in OrderStatementRecord.__table__.columns}


def test_statement_sku_records():
    d = load("order_statement_transactions_settled.json")
    rows = m.map_order_statement_sku_records(d["statement_transactions"][0], record_id=5)
    assert len(rows) == 1
    r = rows[0]
    assert r["external_sku_id"] == "1736823576747934791" and r["quantity"] == 1
    assert r["settlement_amount"] == Decimal(80482) and r["sales_tax_amount"] is None
    assert r["record_id"] == 5 and r["sku_name"] == "Dewasa: 41-47"


def test_order_mapping_and_items():
    orders = load("orders_search_sample.json")["orders"]
    row = m.map_order(orders[0], 1, "IDR")
    assert row["external_order_id"] == "585489904998712566" and row["order_status"] == "COMPLETED"
    assert row["buyer_paid_amount"] == Decimal(124982)
    assert row["gross_merchandise_value"] == Decimal(100000)
    assert row["platform_discount"] == Decimal(2155) and row["shipping_amount"] == Decimal(26500)
    assert row["completed_at"] == datetime.fromtimestamp(1786990000, UTC)
    assert row["raw_source_updated_at"] == datetime.fromtimestamp(1787000000, UTC)
    assert set(row) <= {c.name for c in Order.__table__.columns}
    items = m.map_order_items(orders[0], 42)
    assert len(items) == 1 and items[0]["_external_sku_id"] == "1736823576747934791"
    assert items[0]["gross_item_value"] == Decimal(100000) and items[0]["discounts"] == Decimal(2155)
    cancelled = m.map_order(orders[1], 1, "IDR")
    assert cancelled["cancelled_at"] and cancelled["seller_discount"] == Decimal(5000)
    assert cancelled["gross_merchandise_value"] == Decimal(170000)  # falls back to sub_total
    items2 = m.map_order_items(orders[1], 43)
    assert len(items2) == 2 and all(i["quantity"] == 1 for i in items2)


def test_statement_and_withdrawal_mapping():
    api = {"id": "7676", "statement_time": 1787356800, "revenue_amount": "0", "fee_amount": "0",
           "adjustment_amount": "-64972", "settlement_amount": "-64972", "currency": "IDR",
           "payment_id": "p1", "payment_status": "PAID", "net_sales_amount": "0"}
    row = m.map_statement(api, 1, "IDR")
    assert row["external_settlement_id"] == "7676" and row["net_amount"] == Decimal(-64972)
    assert row["deductions"] == Decimal(-64972) and row["gross_amount"] == Decimal(0)
    assert row["status"] == "PAID" and row["extra"]["payment_id"] == "p1"
    assert set(row) <= {c.name for c in Settlement.__table__.columns}
    w = m.map_withdrawal({"id": "w1", "type": "WITHDRAW", "amount": "150000", "currency": "IDR",
                          "status": "SUCCESS", "create_time": 1787000000}, 1, "IDR")
    assert w["payout_amount"] == Decimal(150000) and w["payout_type"] == "WITHDRAW"
    assert w["initiated_at"] == datetime.fromtimestamp(1787000000, UTC)


def test_analytics_mappings():
    day = date(2026, 8, 29)
    v = {"id": "v1", "title": "t", "username": "u", "video_post_time": 1786780800, "duration": 31,
         "views": "1200", "ctr": "0.034", "gmv": {"amount": "255000", "currency": "IDR"},
         "gpm": {"amount": "212.5", "currency": "IDR"}, "items_sold": 3, "sku_orders": 3}
    vid = m.map_video(v, 1)
    assert vid["external_video_id"] == "v1" and vid["duration_seconds"] == 31
    vm = m.map_video_metric(v, 9, day, NOW)
    assert vm["views"] == 1200 and vm["gmv"] == Decimal(255000) and vm["orders"] == 3
    assert vm["ctr"] == Decimal("0.034") and vm["metric_date"] == day and vm["gpm"] == Decimal("212.5")
    pm = m.map_product_metric({"id": "p", "gmv": {"amount": "1"}, "sku_orders": 2, "items_sold": 4,
                               "click_through_rate": "0.1"}, 3, day, NOW)
    assert pm["orders"] == 2 and pm["units"] == 4 and pm["sku_id"] is None
    sm = m.map_sku_metric({"id": "s", "gmv": "5"}, 3, 8, day, NOW)
    assert sm["sku_id"] == 8 and sm["gmv"] == Decimal(5) and sm["orders"] == 0


def test_catalog_mapping():
    prod = {"id": "17371", "title": "Socks", "status": "ACTIVATE",
            "category_chains": [{"id": "1", "local_name": "Fashion"}, {"id": "2", "local_name": "Socks"}],
            "skus": [{"id": "s1", "seller_sku": "", "price": {"sale_price": "82000"},
                      "sales_attributes": [{"name": "Size", "value_name": "36-40"}]}]}
    p = m.map_product(prod, 1)
    assert p["external_product_id"] == "17371" and p["category"] == "Socks"
    s = m.map_sku(prod["skus"][0], 5)
    assert s["seller_sku"] is None and s["title"] == "36-40" and s["variation_data"]["price"]


def test_build_upsert_compiles_to_on_conflict():
    row = m.map_statement({"id": "1", "statement_time": 1, "settlement_amount": "5"}, 1, "IDR")
    stmt = build_upsert(Settlement, [row], ["shop_id", "external_settlement_id"])
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (shop_id, external_settlement_id) DO UPDATE SET" in sql
    assert "extra = excluded.extra" in sql and "shop_id = excluded" not in sql
    assert build_upsert(Settlement, [], ["shop_id"]) is None
    only_keys = build_upsert(Settlement, [{"shop_id": 1, "external_settlement_id": "x"}],
                             ["shop_id", "external_settlement_id"])
    assert "DO NOTHING" in str(only_keys.compile(dialect=postgresql.dialect()))
    items = build_upsert(Order, [{"shop_id": 1, "external_order_id": "o", "_tmp": 1,
                                  "currency": "IDR", "order_status": "X",
                                  "order_created_at": NOW}], ["shop_id", "external_order_id"])
    assert "_tmp" not in str(items.compile(dialect=postgresql.dialect()))


def test_migration_covers_model_columns():
    src = (Path(__file__).parents[2] / "migrations" / "versions"
           / "b4e7a2c91d03_finance_records_shop_metrics.py").read_text()
    assert "down_revision: str | Sequence[str] | None = '8d1c1fc758d5'" in src
    from src.db.models_finance import OrderStatementSkuRecord
    for model in (OrderStatementRecord, OrderStatementSkuRecord, ShopMetric):
        assert f"'{model.__tablename__}'" in src
        for c in model.__table__.columns:
            assert f'"{c.name}"' in src or f"'{c.name}'" in src, (model.__tablename__, c.name)
    assert "'extra'" in src and "'payout_type'" in src
    assert hasattr(Settlement, "extra") and "extra" in Settlement.__table__.columns


def test_ts_parses_datetime_string_in_shop_tz():
    from datetime import UTC, datetime

    from src.domain.ingest.mappers import ts
    d = ts("2026-07-04 09:16:58")
    assert d == datetime(2026, 7, 4, 2, 16, 58, tzinfo=UTC)
    assert ts("1787356800") == datetime.fromtimestamp(1787356800, UTC)
    assert ts("2026-07-04T09:16:58Z") == datetime(2026, 7, 4, 9, 16, 58, tzinfo=UTC)


def test_map_shop_metric_live_shape():
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from src.domain.ingest.mappers import map_shop_metric
    api = {"performance": {"intervals": [{"sales": {"gmv": {"overall": {"amount": "419408.00", "currency": "IDR"},
            "breakdowns": [{"gmv": {"amount": "0.00", "currency": "IDR"}, "type": "LIVE"},
                           {"gmv": {"amount": "160978.00", "currency": "IDR"}, "type": "VIDEO"},
                           {"gmv": {"amount": "258430.00", "currency": "IDR"}, "type": "PRODUCT_CARD"}]},
            "refunds": {"amount": "0.00", "currency": "IDR"}, "items_sold": 5, "orders_count": 5,
            "gross_revenue": {"overall": {"amount": "425632.00", "currency": "IDR"},
                              "breakdowns": [{"type": "GMV_MAX", "percentage": "0.9995"}, {"type": "NON_GMV_MAX", "percentage": "0.0005"}]},
            "sku_orders_count": 5, "avg_customers_count": 5},
            "traffic": {"avg_visitors": 36}, "end_date": "2026-08-30", "start_date": "2026-08-29"}]}, "latest_available_date": "2026-08-29"}
    m = map_shop_metric(api, 1, date(2026, 8, 29), datetime.now(UTC))
    assert m["gmv_total"] == Decimal("419408.00") and m["gmv_video"] == Decimal("160978.00")
    assert m["gross_revenue_gmv_max_pct"] == Decimal("0.9995") and m["sku_orders"] == 5
    assert m["gross_revenue_gmv_max"] == Decimal("425632.00") * Decimal("0.9995")
