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
    ctx = NS(shop=NS(id=1, timezone="Asia/Jakarta"))
    with patch.object(S.ingest, "sync_orders", lambda c: calls.append("orders") or {}), \
         patch.object(S.ingest, "sync_order_statements", lambda c: calls.append("ostm") or {}), \
         patch.object(S.ingest, "sync_statements", lambda c: calls.append("stm") or {}), \
         patch.object(S.profit, "compute_order_profits",
                      lambda s, sid: calls.append("profit") or {"dates": [], "orders": 0}), \
         patch.object(S.aggregates, "recompute_daily",
                      lambda s, sid, d, tz: calls.append(("agg", tz)) or {}):
        out = S.finance_cycle(MagicMock(), lambda s: ctx)
    assert calls == ["orders", "ostm", "stm", "profit", ("agg", "Asia/Jakarta")]
    assert out["profit"] == {"orders": 0}


def test_build_scheduler_jobs_and_timezone():
    sched = S.build_scheduler(lambda name: None, tz="Asia/Jakarta")
    ids = {j.id: j for j in sched.get_jobs()}
    assert set(ids) == {"finance_cycle", "withdrawals", "daily_metrics"}
    assert str(sched.timezone) == "Asia/Jakarta"
    assert ids["finance_cycle"].next_run_time <= datetime.now(UTC)
    assert "hour='3'" in str(ids["daily_metrics"].trigger)


def test_collect_errors_nested():
    out = {"a": {"error": "E1"}, "b": {"c": {"error": "E2"}, "d": 1}, "profit": {"errors": []}}
    assert S._collect_errors(out) == ["a: E1", "b.c: E2"]
