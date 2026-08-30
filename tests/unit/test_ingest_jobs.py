"""Mock-based tests for src.domain.ingest.jobs / raw_store / upserts (no DB)."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.db.models import OrderItem
from src.domain.ingest import jobs
from src.domain.ingest.mappers import map_order_items
from src.domain.ingest.raw_store import DbRawSink
from src.domain.ingest.upserts import build_upsert, dedupe_rows
from src.integrations.sync_state import SyncStateStore

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
J = "src.domain.ingest.jobs"


def make_ctx(cursor: str | None = None, resource: str = "orders") -> jobs.IngestContext:
    shop = MagicMock(id=1, currency="IDR", timezone="Asia/Jakarta")
    state = SyncStateStore()
    if cursor:
        state.mark_success(jobs.INTEGRATION, resource, "1", cursor)
    sink = MagicMock(last_id=42, count=0)
    return jobs.IngestContext(session=MagicMock(), client=MagicMock(), shop=shop, sink=sink,
                              state=state, now=NOW)


# --- _run ------------------------------------------------------------------------
def test_run_success_commits_and_sets_cursor():
    ctx = make_ctx()
    out = jobs._run(ctx, "orders", lambda c: ("2026-08-30T00:00:00+00:00", {"orders": 3}))
    assert out == {"orders": 3}
    ctx.session.commit.assert_called_once()
    st = ctx.state.get(jobs.INTEGRATION, "orders", "1")
    assert st.status == "success" and st.cursor == "2026-08-30T00:00:00+00:00"


def test_run_error_rolls_back_and_returns_error():
    ctx = make_ctx(cursor="keep")

    def boom(c):
        raise RuntimeError("api down")
    out = jobs._run(ctx, "orders", boom)
    assert out == {"error": "RuntimeError: api down"}
    ctx.session.rollback.assert_called_once()
    ctx.session.commit.assert_not_called()
    st = ctx.state.get(jobs.INTEGRATION, "orders", "1")
    assert st.status == "error" and st.cursor == "keep" and "api down" in st.error


def test_run_survives_mark_error_failure():
    ctx = make_ctx()
    ctx.state.mark_error = MagicMock(side_effect=RuntimeError("db gone"))

    def boom(c):
        raise ValueError("x")
    assert jobs._run(ctx, "orders", boom) == {"error": "ValueError: x"}


# --- ensure_shop -------------------------------------------------------------------
def test_ensure_shop_unknown_cipher_raises():
    client = MagicMock()
    client.get_authorized_shops.return_value = [{"id": "s1", "cipher": "c1"}]
    with pytest.raises(ValueError, match="shop_cipher"):
        jobs.ensure_shop(MagicMock(), client, MagicMock(), currency="IDR",
                         timezone="Asia/Jakarta", shop_cipher="other")


def test_ensure_shop_no_shops_raises():
    client = MagicMock()
    client.get_authorized_shops.return_value = []
    with pytest.raises(RuntimeError):
        jobs.ensure_shop(MagicMock(), client, MagicMock(), currency="IDR", timezone="x")


# --- sync_orders routing -----------------------------------------------------------
UPD = NOW - timedelta(days=1)
ORDER = {"id": "o1", "create_time": int((NOW - timedelta(days=2)).timestamp()),
         "update_time": int(UPD.timestamp()), "status": "COMPLETED",
         "payment": {"total_amount": "100"}, "line_items": [{"id": "li1", "sku_id": "s", "product_id": "p",
                                                             "sale_price": "100"}]}


@patch(f"{J}._upsert_order_items")
@patch(f"{J}.product_ids", return_value={})
@patch(f"{J}.sku_ids", return_value={})
@patch(f"{J}.upsert_map", return_value={"o1": 11})
def test_sync_orders_since_uses_create_time(um, _s, _p, items):
    ctx = make_ctx(cursor="2026-08-20T00:00:00+00:00")
    ctx.client.get_orders.return_value = iter([ORDER])
    since = NOW - timedelta(days=5)
    out = jobs.sync_orders(ctx, since=since)
    kw = ctx.client.get_orders.call_args.kwargs
    assert kw == {"create_time_ge": int(since.timestamp()), "create_time_lt": int(NOW.timestamp())}
    assert out["orders"] == 1
    items.assert_called_once()
    assert items.call_args.args[1] == 11
    # cursor = max(prev, update_time)
    assert ctx.state.get(jobs.INTEGRATION, "orders", "1").cursor == UPD.isoformat()


@patch(f"{J}._upsert_order_items")
@patch(f"{J}.product_ids", return_value={})
@patch(f"{J}.sku_ids", return_value={})
@patch(f"{J}.upsert_map", return_value={"o1": 11})
def test_sync_orders_incremental_uses_update_time_from_cursor(um, _s, _p, _i):
    cur = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)
    ctx = make_ctx(cursor=cur.isoformat())
    ctx.client.get_orders.return_value = iter([])
    out = jobs.sync_orders(ctx)
    kw = ctx.client.get_orders.call_args.kwargs
    assert set(kw) == {"update_time_ge", "update_time_lt"}
    assert kw["update_time_ge"] == int((cur - timedelta(hours=1)).timestamp())
    assert out["orders"] == 0
    assert ctx.state.get(jobs.INTEGRATION, "orders", "1").cursor == cur.isoformat()


# --- order items ---------------------------------------------------------------------
def test_map_order_items_synthesizes_unique_ids():
    api = {"line_items": [{"id": "a", "sale_price": "1"}, {"id": "a", "sale_price": "1"},
                          {"sale_price": "1"}]}
    ids = [i["external_item_id"] for i in map_order_items(api, 7)]
    assert ids == ["a", "7:1", "7:2"] and len(set(ids)) == 3


@patch(f"{J}.upsert")
def test_upsert_order_items_deletes_missing_only(up):
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    items = [{"order_id": 7, "external_item_id": "a", "quantity": 1}]
    jobs._upsert_order_items(session, 7, items)
    up.assert_called_once_with(session, OrderItem, items, ["order_id", "external_item_id"])
    stmt = session.execute.call_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert sql.startswith("DELETE FROM order_items") and "NOT IN ('a')" in sql


# --- statements: which orders to poll ---------------------------------------------------
def poll(**kw):
    base = {"order_status": "COMPLETED", "order_updated_at": None, "has_settled": False,
            "max_fetched_at": None, "latest_statement_time": None, "now": NOW}
    return jobs.needs_statement_poll(**{**base, **kw})


def test_needs_statement_poll_cases():
    assert not poll(order_status="UNPAID")
    assert poll(order_status="CANCELLED")  # cancelled-with-fees: still polled until settled
    assert poll(order_status="CANCELLED", has_settled=True,
                latest_statement_time=NOW - timedelta(days=3))
    assert not poll(order_status="CANCELLED", has_settled=True,
                    latest_statement_time=NOW - timedelta(days=40))
    # settled then refunded: order updated after our last fetch
    assert poll(has_settled=True, max_fetched_at=NOW - timedelta(days=45),
                order_updated_at=NOW - timedelta(days=2),
                latest_statement_time=NOW - timedelta(days=50))
    # settled long ago, untouched since -> skip
    assert not poll(has_settled=True, max_fetched_at=NOW - timedelta(days=45),
                    order_updated_at=NOW - timedelta(days=60),
                    latest_statement_time=NOW - timedelta(days=50))


def test_orders_needing_statement_filters_rows():
    ctx = make_ctx()
    ctx.session.execute.return_value = [
        ("o-unpaid", "UNPAID", None, None, None, None),
        ("o-new", "COMPLETED", None, None, None, None),
        ("o-old", "COMPLETED", NOW - timedelta(days=60), True, NOW - timedelta(days=45),
         NOW - timedelta(days=50)),
        ("o-recent", "COMPLETED", None, True, NOW - timedelta(days=5), NOW - timedelta(days=6)),
    ]
    assert jobs._orders_needing_statement(ctx, 90) == ["o-new", "o-recent"]


# --- sync_order_statements ---------------------------------------------------------
REC = {"id": "t1", "statement_id": "st1", "status": "SETTLED", "settlement_amount": "10",
       "sku_statement_transactions": [{"sku_id": "s1", "settlement_amount": "10"}]}


@patch(f"{J}._drop_placeholder_record")
@patch(f"{J}.upsert")
@patch(f"{J}.upsert_map", return_value={"st1": 5})
def test_sync_order_statements_records_and_empty(um, up, drop):
    ctx = make_ctx(resource="order_statements")
    ctx.client.get_order_statement_transactions.side_effect = [
        {"statement_transactions": [REC], "order_create_time": 1756500000},
        {"statement_transactions": []}]
    out = jobs.sync_order_statements(ctx, ["o1", "o2"])
    assert out == {"orders_polled": 2, "records": 1, "sku_records": 1, "no_statement_yet": 1}
    rows = um.call_args.args[2]
    assert rows[0]["raw_response_id"] == 42 and rows[0]["fetched_at"] == NOW
    assert rows[0]["settlement_amount"] == Decimal(10)
    drop.assert_called_once_with(ctx, "o1")


@patch(f"{J}._drop_placeholder_record")
@patch(f"{J}.upsert")
@patch(f"{J}.upsert_map", return_value={"": 5})
def test_sync_order_statements_placeholder_not_dropped_for_unsettled(um, up, drop):
    ctx = make_ctx(resource="order_statements")
    ctx.client.get_order_statement_transactions.return_value = {
        "statement_transactions": [{"id": "t1", "status": "UNSETTLED"}]}
    jobs.sync_order_statements(ctx, ["o1"])
    drop.assert_not_called()


@patch(f"{J}._orders_needing_statement", return_value=["x"])
def test_sync_order_statements_default_selection(sel):
    ctx = make_ctx(resource="order_statements")
    ctx.client.get_order_statement_transactions.return_value = {"statement_transactions": []}
    out = jobs.sync_order_statements(ctx, unsettled_days=30)
    sel.assert_called_once_with(ctx, 30)
    assert out["no_statement_yet"] == 1


# --- sync_metrics ------------------------------------------------------------------
@patch(f"{J}.upsert")
def test_sync_metrics_iterates_days_and_advances_cursor(up):
    ctx = make_ctx(cursor="2026-08-27", resource="shop_metrics")
    ctx.client.get_shop_performance.return_value = {}
    out = jobs.sync_metrics(ctx, days=60, resources=("shop_metrics",))
    # today local (Jakarta) = 2026-08-30 -> last day 08-29; cursor 08-27 - 2 resync = 08-25
    assert out["shop_metrics"] == {"shop_metrics": 5, "days": 5}
    calls = [c.args for c in ctx.client.get_shop_performance.call_args_list]
    assert calls[0] == ("2026-08-25", "2026-08-26") and calls[-1] == ("2026-08-29", "2026-08-30")
    assert ctx.session.commit.call_count == 6  # per day + final
    assert ctx.state.get(jobs.INTEGRATION, "shop_metrics", "1").cursor == "2026-08-29"


@patch(f"{J}.upsert")
def test_sync_metrics_nothing_to_do_keeps_cursor(up):
    ctx = make_ctx(cursor="2026-08-29", resource="shop_metrics")
    ctx.now = datetime(2026, 8, 30, 0, 30, tzinfo=UTC)  # still 08-30 in Jakarta
    ctx.state.mark_success(jobs.INTEGRATION, "shop_metrics", "1", "2026-08-29")
    out = jobs.sync_metrics(ctx, days=1, resources=("shop_metrics",))
    assert out["shop_metrics"]["days"] == 3  # resync window
    assert ctx.today_local() == date(2026, 8, 30)


# --- DbRawSink ---------------------------------------------------------------------
def test_db_raw_sink_last_id_and_count():
    session = MagicMock()
    ids = iter([7, 8])
    session.add.side_effect = lambda row: setattr(row, "id", next(ids))
    sink = DbRawSink(session, 1)
    assert sink.last_id is None
    sink("orders", {"page": 1}, {"data": {}})
    assert sink.last_id == 7 and sink.count == 1
    sink("orders", {"page": 2}, {"data": {}})
    assert sink.last_id == 8 and sink.count == 2
    assert session.commit.call_count == 2
    assert session.add.call_args.args[0].shop_id == 1


# --- upserts -----------------------------------------------------------------------
def test_dedupe_rows_last_wins():
    rows = [{"a": 1, "b": "x", "v": 1}, {"a": 2, "b": "x", "v": 2}, {"a": 1, "b": "x", "v": 3}]
    assert dedupe_rows(rows, ["a", "b"]) == [{"a": 1, "b": "x", "v": 3}, {"a": 2, "b": "x", "v": 2}]


def test_build_upsert_dedupes_conflict_key():
    rows = [{"order_id": 1, "external_item_id": "a", "quantity": 1, "_tmp": 0},
            {"order_id": 1, "external_item_id": "a", "quantity": 2}]
    stmt = build_upsert(OrderItem, rows, ["order_id", "external_item_id"])
    params = stmt.compile().params
    assert "quantity_m1" not in params and params["quantity_m0"] == 2  # single row, last wins
