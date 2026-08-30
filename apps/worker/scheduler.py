"""APScheduler jobs (shop-local time). Each job = one DB session; result/errors recorded in
integration_sync_state as resource `job:<name>` so /health can report last runs."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from src.config.settings import settings
from src.domain.ingest import jobs as ingest
from src.domain.ingest.state import DbSyncStateStore
from src.domain.profit import aggregates
from src.domain.profit import jobs as profit

log = logging.getLogger("tt.scheduler")
JOB_INTEGRATION = "tt"
METRICS_RESYNC_DAYS = 3  # daily analytics: refetch last N days (D-1 restates)


def _compute_profit(session: Any, shop: Any) -> dict[str, Any]:
    res = profit.compute_order_profits(session, shop.id)  # full run: small shop, always consistent
    agg = aggregates.recompute_daily(session, shop.id, res["dates"] or None,
                                     shop.timezone or profit.DEFAULT_TZ)
    return {"profit": {k: v for k, v in res.items() if k != "dates"}, "aggregates": agg}


def finance_cycle(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    """Hourly: orders -> per-order statements -> statements -> profit + aggregates."""
    ctx = build_context(session)
    out = {"orders": ingest.sync_orders(ctx), "order_statements": ingest.sync_order_statements(ctx),
           "statements": ingest.sync_statements(ctx)}
    out.update(_compute_profit(session, ctx.shop))
    return out


def withdrawals(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    ctx = build_context(session)
    return {"withdrawals": ingest.sync_withdrawals(ctx)}


def daily_metrics(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    """03:00 shop time: catalog + analytics (last METRICS_RESYNC_DAYS) then profit recompute."""
    ctx = build_context(session)
    out = {"catalog": ingest.sync_catalog(ctx), "metrics": ingest.sync_metrics(ctx, days=METRICS_RESYNC_DAYS)}
    out.update(_compute_profit(session, ctx.shop))
    return out


JOBS: dict[str, Callable[[Any, Callable[[Any], Any]], dict[str, Any]]] = {
    "finance_cycle": finance_cycle, "withdrawals": withdrawals, "daily_metrics": daily_metrics,
}


def run_job(name: str, session_factory: Callable[[], Any], build_context: Callable[[Any], Any],
            shop_lookup: Callable[[Any], Any]) -> dict[str, Any]:
    """Runs one named job in its own session; never raises (scheduler must keep going)."""
    fn = JOBS[name]
    started = datetime.now(UTC)
    with session_factory() as session:
        store, key = DbSyncStateStore(session), None
        try:
            shop = shop_lookup(session)
            key = (JOB_INTEGRATION, f"job:{name}", str(shop.id))
            store.start_attempt(*key)
        except Exception:
            log.exception("job %s: cannot resolve shop/state", name)
        try:
            out = fn(session, build_context)
            errors = _collect_errors(out)
            if key:
                if errors:
                    store.mark_error(*key, "; ".join(errors))
                else:
                    store.mark_success(*key, started.isoformat(timespec="seconds"))
            log.info("job %s done in %.1fs errors=%d", name, (datetime.now(UTC) - started).total_seconds(),
                     len(errors))
            return out
        except Exception as e:
            session.rollback()
            log.exception("job %s failed", name)
            if key:
                try:
                    store.mark_error(*key, f"{type(e).__name__}: {e}")
                except Exception:
                    log.exception("job %s: mark_error failed", name)
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


def _collect_errors(out: Any, path: str = "") -> list[str]:
    """Sub-job dicts return {"error": ...} instead of raising -> surface them in job state."""
    errs: list[str] = []
    if isinstance(out, dict):
        if "error" in out and isinstance(out["error"], str):
            errs.append(f"{path or 'job'}: {out['error'][:200]}")
        for k, v in out.items():
            if k != "error":
                errs += _collect_errors(v, f"{path}.{k}" if path else str(k))
    return errs


def build_scheduler(runner: Callable[[str], Any], tz: str | None = None):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    tz = tz or settings.shop_timezone
    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 600}
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(runner, IntervalTrigger(hours=1, timezone=tz), args=["finance_cycle"],
                  id="finance_cycle", next_run_time=datetime.now(UTC), **common)
    sched.add_job(runner, IntervalTrigger(hours=6, timezone=tz), args=["withdrawals"],
                  id="withdrawals", next_run_time=datetime.now(UTC), **common)
    sched.add_job(runner, CronTrigger(hour=3, minute=0, timezone=tz), args=["daily_metrics"],
                  id="daily_metrics", **common)
    return sched
