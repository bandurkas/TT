"""Run only against an explicitly named disposable PostgreSQL test database."""
import os
from datetime import date, datetime
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

URL = os.environ.get("ORDER_LEDGER_TEST_DATABASE_URL")
if not URL:
    pytest.skip("ORDER_LEDGER_TEST_DATABASE_URL is not set", allow_module_level=True)
if make_url(URL).database != "order_journal_test":
    raise RuntimeError("Order journal integration tests require a disposable order_journal_test database")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import dashboard as A
from src.db.base import Base
from src.db.models import Order, OrderItem, OrderProfit, Product, Shop, Sku
from src.db.models_finance import OrderStatementRecord
from src.domain.dashboard import order_loaders as L
from tests.unit.test_order_journal import sample

START, END = date(2026, 8, 1), date(2026, 8, 31)


@pytest.fixture(scope="module")
def engine():
    e = create_engine(URL)
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        session.add_all([Shop(id=i, external_shop_id=f"test-{i}", name=f"Shop {i}", currency="IDR",
                              timezone="Asia/Jakarta", region="ID") for i in (1, 2)])
        session.flush()
        session.add_all([Product(id=i, shop_id=i, external_product_id=f"p-{i}", title="Cream 10%_green") for i in (1, 2)])
        session.flush()
        session.add(Sku(id=1, product_id=1, external_sku_id="SKU-A", title="Large"))
        orders = [(1, 1, "2026-08-01T00:00:00+07:00"), (2, 1, "2026-08-31T23:59:59+07:00"),
                  (3, 1, "2026-08-20T10:00:00+07:00"), (4, 1, "2026-07-31T23:59:59+07:00"),
                  (5, 1, "2026-09-01T00:00:00+07:00"), (6, 2, "2026-08-15T10:00:00+07:00")]
        session.add_all([Order(id=i, shop_id=s, external_order_id=f"external-{i}",
                               order_created_at=datetime.fromisoformat(at), order_status="COMPLETED", currency="IDR")
                         for i, s, at in orders])
        session.flush()
        session.add(OrderItem(id=1, order_id=1, product_id=1, sku_id=1, quantity=2))
        _, p, records = sample()
        session.add(OrderProfit(order_id=1, is_current=True, **vars(p)))
        old = {**vars(p), "version": 2, "estimated_net_profit": D(999999)}
        session.add(OrderProfit(order_id=1, is_current=False, **old))
        preliminary = {**vars(p), "inputs_snapshot": {"source": "ratio_estimate", "fee_ratio": None},
                       "profit_status": "PROVISIONAL", "estimated_net_profit": D(-10000)}
        for i in (2, 4, 5, 6):
            session.add(OrderProfit(order_id=i, is_current=True, **preliminary))
        for r in records:
            session.add(OrderStatementRecord(shop_id=1, external_order_id="external-1", **vars(r)))
        session.add(OrderStatementRecord(shop_id=2, external_order_id="external-1", **vars(records[0])))
        session.flush()
        yield session
        session.rollback()


def page(db, **kwargs):
    return L.page(db, 1, START, END, "Asia/Jakarta", **kwargs)


def test_date_boundaries_versions_and_totals_are_independent_of_pagination(db):
    p = page(db, limit=1)
    assert p["total"] == 3 and [r["id"] for r in p["rows"]] == [2]
    assert p["summary"]["calculated_orders"] == 2 and p["summary"]["missing_orders"] == 1
    assert p["summary"]["net_profit"] == D(19200)
    assert page(db, limit=1, offset=2)["rows"][0]["id"] == 1
    assert page(db, limit=1, offset=2)["summary"] == p["summary"]
    assert page(db, offset=200)["rows"] == []


def test_filters_search_escape_and_final_source_are_consistent(db):
    assert [r["id"] for r in page(db, state="final")["rows"]] == [1]
    assert [r["id"] for r in page(db, state="preliminary")["rows"]] == [2]
    assert [r["id"] for r in page(db, state="not_calculated")["rows"]] == [3]
    assert [r["id"] for r in page(db, loss_only=True)["rows"]] == [2]
    assert page(db, search="10%_green")["rows"][0]["id"] == 1
    assert page(db, search="10XXgreen")["rows"] == []
    assert page(db, search="external-2")["total"] == 1
    assert page(db, search="'")["rows"] == []


def test_detail_is_shop_scoped_and_source_linked(db):
    d = L.detail(db, 1, 1)
    assert d["version"] == 3 and len(d["settlements"]) == 2
    assert d["settlement_check"]["status"] == "matched"
    assert d["items"][0] == {"title": "Cream 10%_green", "sku_id": "SKU-A", "sku_title": "Large", "quantity": 2}
    with pytest.raises(LookupError):
        L.detail(db, 2, 1)
    assert L.detail(db, 1, 3)["amounts"] is None


def test_mixed_currencies_are_not_summed(db):
    db.query(OrderProfit).filter_by(order_id=2, is_current=True).one().currency = "USD"
    db.flush()
    p = page(db)
    assert p["mixed_currencies"] is True and p["summary"] is None


def test_http_contract_validation_and_not_found(db):
    app = FastAPI()
    app.include_router(A.router)
    app.dependency_overrides[A.get_session] = lambda: db
    with TestClient(app) as c:
        query = "shop_id=1&from=2026-08-01&to=2026-08-31"
        response = c.get(f"/api/orders?{query}&limit=1")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["summary"]["net_profit"] == "19200" and body["total"] == 3
        assert c.get("/api/orders/1?shop_id=1").json()["settlement_check"]["actual"] == "68200"
        assert c.get("/api/orders/1?shop_id=2").status_code == 404
        assert c.get("/api/orders/999?shop_id=1").status_code == 404
        assert c.get("/api/orders?shop_id=999").status_code == 404
        for invalid in ("limit=0", "limit=101", "offset=-1", "state=bogus", "search=" + "x" * 101):
            assert c.get(f"/api/orders?{query}&{invalid}").status_code == 422
