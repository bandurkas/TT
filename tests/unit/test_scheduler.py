from datetime import UTC, datetime
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from apps.worker import scheduler as S


class FakeStore:
    def __init__(self, session):
        self.calls = []
        session.store = self

    def start_attempt(self, *k):
        self.calls.append(("start", k))

    def mark_success(self, *k):
        self.calls.append(("success", k))

    def mark_error(self, *k):
        self.calls.append(("error", k))


class FakeSession:
    def __init__(self):
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def rollback(self):
        self.rolled_back = True


def _run(name, fn, out):
    sess = FakeSession()
    with patch.object(S, "DbSyncStateStore", FakeStore), patch.dict(S.JOBS, {name: fn}):
        res = S.run_job(name, lambda: sess, lambda s: NS(shop=NS(id=1)), lambda s: NS(id=1))
    return res, sess


def test_run_job_marks_success():
    res, sess = _run("finance_cycle", lambda s, b: {"orders": {"n": 1}}, None)
    assert res == {"orders": {"n": 1}}
    kinds = [c[0] for c in sess.store.calls]
    assert kinds == ["start", "success"]
    assert sess.store.calls[0][1] == ("tt", "job:finance_cycle", "1")


def test_run_job_sub_error_marks_error_without_raising():
    res, sess = _run("withdrawals", lambda s, b: {"withdrawals": {"error": "RuntimeError: x"}}, None)
    assert res["withdrawals"]["error"].startswith("RuntimeError")
    assert sess.store.calls[-1][0] == "error" and "withdrawals: RuntimeError" in sess.store.calls[-1][1][3]


def test_run_job_exception_rolls_back_and_marks_error():
    def boom(s, b):
        raise ValueError("bad")
    res, sess = _run("daily_metrics", boom, None)
    assert res == {"error": "ValueError: bad"} and sess.rolled_back
    assert sess.store.calls[-1] == ("error", ("tt", "job:daily_metrics", "1", "ValueError: bad"))


def test_finance_cycle_order_of_calls():
    calls = []
    ctx = NS(shop=NS(id=1, timezone="Asia/Jakarta", currency="IDR"))
    with patch.object(S.ingest, "sync_orders", lambda c: calls.append("orders") or {}), \
         patch.object(S.ingest, "sync_statements", lambda c: calls.append("stm") or {}), \
         patch.object(S.product_costs, "rebuild_cost_versions",
                      lambda s, sid, cur, tz: calls.append(("costs", cur, tz)) or
                      {"skus_with_lots": 0, "versions": 0}), \
         patch.object(S.profit, "compute_order_profits",
                      lambda s, sid: calls.append("profit") or {"dates": [], "orders": 0}), \
         patch.object(S.aggregates, "recompute_daily",
                      lambda s, sid, d, tz: calls.append(("agg", tz)) or {}):
        out = S.finance_cycle(MagicMock(), lambda s: ctx)
    # cost lots (FIFO batches) must be rebuilt BEFORE profit compute, so newly exhausted lots apply
    assert calls == ["orders", "stm", ("costs", "IDR", "Asia/Jakarta"), "profit", ("agg", "Asia/Jakarta")]
    assert out["profit"] == {"orders": 0} and out["cost_versions"] == {"skus_with_lots": 0, "versions": 0}


def test_order_statements_job_uses_poll_horizon():
    seen = {}
    ctx = NS(shop=NS(id=1, timezone=None, currency="IDR"))
    with patch.object(S.ingest, "sync_order_statements",
                      lambda c, unsettled_days: seen.setdefault("days", unsettled_days) or {}), \
         patch.object(S.product_costs, "rebuild_cost_versions",
                      lambda s, sid, cur, tz: {"skus_with_lots": 0, "versions": 0}), \
         patch.object(S.profit, "compute_order_profits", lambda s, sid: {"dates": []}), \
         patch.object(S.aggregates, "recompute_daily", lambda s, sid, d, tz: {"tz": tz}):
        out = S.order_statements(MagicMock(), lambda s: ctx)
    assert seen["days"] == S.STATEMENT_POLL_DAYS and out["aggregates"] == {"tz": "Asia/Jakarta"}


def test_build_scheduler_fixed_slots_single_executor():
    sched = S.build_scheduler(lambda name: None, tz="Asia/Jakarta", immediate=True)
    ids = {j.id: j for j in sched.get_jobs()}
    assert set(ids) == set(S.SLOTS) == {"finance_cycle", "order_statements", "withdrawals", "daily_metrics"}
    assert str(sched.timezone) == "Asia/Jakarta"
    assert ids["finance_cycle"].next_run_time <= datetime.now(UTC)
    assert getattr(ids["withdrawals"], "next_run_time", None) is None  # scheduled at start, not now
    assert "hour='3'" in str(ids["daily_metrics"].trigger)
    assert "minute='5'" in str(ids["finance_cycle"].trigger)
    assert sched._executors["default"]._pool._max_workers == 1
    lazy = S.build_scheduler(lambda name: None, tz="Asia/Jakarta", immediate=False)
    assert getattr({j.id: j for j in lazy.get_jobs()}["finance_cycle"], "next_run_time", None) is None


def test_run_job_serialised_by_lock():
    assert S._LOCK.acquire(blocking=False)
    try:
        import threading
        done = []
        t = threading.Thread(target=lambda: done.append(
            _run("withdrawals", lambda s, b: {"ok": 1}, None)))
        t.start()
        t.join(0.2)
        assert t.is_alive() and not done  # blocked on the lock
    finally:
        S._LOCK.release()
    t.join(2)
    assert done and done[0][0] == {"ok": 1}


def test_collect_errors_nested_and_lists():
    out = {"a": {"error": "E1"}, "b": {"c": {"error": "E2"}, "d": 1},
           "profit": {"errors": ["order 1: CurrencyMismatchError: x", "order 2: y"], "skipped": 2}}
    assert S._collect_errors(out) == ["a: E1", "b.c: E2",
                                      "profit: 2 errors: order 1: CurrencyMismatchError: x"]
    assert S._collect_errors({"profit": {"errors": []}}) == []


def test_reset_stuck_jobs_and_finance_due():
    from datetime import timedelta
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    stuck = NS(status="running", error=None)
    session = MagicMock()
    session.scalars.return_value = [stuck]
    assert S.reset_stuck_jobs(session, now) == 1
    assert stuck.status == "error" and "interrupted" in stuck.error
    session.commit.assert_called_once()
    session.scalar.return_value = None
    assert S.finance_due(session, now)
    session.scalar.return_value = NS(last_successful_sync=now - timedelta(minutes=10))
    assert not S.finance_due(session, now)
    session.scalar.return_value = NS(last_successful_sync=now - timedelta(hours=2))
    assert S.finance_due(session, now)
