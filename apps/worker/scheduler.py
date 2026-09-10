"""APScheduler jobs (shop-local time). Each job = one DB session; result/errors recorded in
integration_sync_state as resource `job:<name>` so /health can report last runs.
Jobs are serialised with a process lock: profit compute must never run twice concurrently."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from src.config.settings import settings
from src.db.models import IntegrationSyncState
from src.domain import costs as product_costs
from src.domain.ingest import jobs as ingest
from src.domain.ingest.state import DbSyncStateStore
from src.domain.profit import aggregates
from src.domain.profit import jobs as profit

log = logging.getLogger("tt.scheduler")
JOB_INTEGRATION = "tt"
METRICS_RESYNC_DAYS = 3  # daily analytics: refetch last N days (D-1 restates)
STATEMENT_POLL_DAYS = 45  # per-order statement re-poll horizon
_LOCK = threading.Lock()

# fixed slots (shop tz) so restarts never drift the hourly job onto the daily one
SLOTS: dict[str, dict[str, Any]] = {
    "finance_cycle": {"minute": 5},
    "order_statements": {"hour": "*/6", "minute": 40},
    "withdrawals": {"hour": "*/6", "minute": 20},
    "daily_metrics": {"hour": 3, "minute": 0},
    "ads_windsor": {"minute": 25},
    # Every 15 minutes: this source reports the day in progress, and the dashboard shows it as a
    # reading with a timestamp. Windsor stays on its hourly slot as an independent cross-check.
    "ads_tiktok": {"minute": "*/15"},
}
# /health: a job older than this (or stuck "running") is stale
STALE_AFTER = {"finance_cycle": timedelta(hours=3), "order_statements": timedelta(hours=13),
               "withdrawals": timedelta(hours=13), "daily_metrics": timedelta(hours=27),
               "ads_windsor": timedelta(hours=3), "ads_tiktok": timedelta(minutes=90)}


def _compute_profit(session: Any, shop: Any) -> dict[str, Any]:
    tz = shop.timezone or profit.DEFAULT_TZ
    rebuilt = product_costs.rebuild_cost_versions(session, shop.id, shop.currency, tz)
    res = profit.compute_order_profits(session, shop.id)  # full run: small shop, always consistent
    agg = aggregates.recompute_daily(session, shop.id, res["dates"] or None,
                                     shop.timezone or profit.DEFAULT_TZ)
    return {"cost_versions": {k: rebuilt[k] for k in ("skus_with_lots", "versions")},
            "profit": {k: v for k, v in res.items() if k != "dates"}, "aggregates": agg}


def ads_windsor(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    """Hourly: GMV Max daily Cost per campaign from Windsor.ai, for days that have already ended.
    Skipped, not failed, when no key is configured. See docs/windsor-ingest.md."""
    from src.domain.ads import windsor as W
    from src.integrations.windsor.client import WindsorClient

    if not settings.windsor_api_key:
        return {"skipped": "WINDSOR_API_KEY not configured"}
    if _tiktok_ads_ready():
        # Both sources write the same ShopAdDay rows. Left running, they would restate each other
        # every hour, each insert a SourceReport and force a profit recompute. The Ads API is the
        # authoritative one, so Windsor stands down while it is live.
        return {"skipped": "superseded by the TikTok Ads API"}
    ctx = build_context(session)
    shop = ctx.shop
    start, end = W.window(shop.timezone or "Asia/Jakarta", settings.windsor_backfill_days)
    rows, meta = WindsorClient(settings.windsor_api_key).fetch_gmv_max(start, end)
    out = W.ingest(session, shop, rows, meta)
    if out.get("written"):
        out.update(_compute_profit(session, shop))
    return out


def _tiktok_ads_ready() -> bool:
    """Configured *and* authorised: an app id alone writes nothing."""
    from src.integrations.tiktok_shop.auth import TokenStore
    if not settings.tiktok_ads_app_id:
        return False
    tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load()
    return bool(tok and tok.get("access_token") and tok.get("advertiser_ids"))


def ads_tiktok(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    """Every 15 min: GMV Max Cost per campaign from TikTok's own Ads API, including the open day.
    Skipped, not failed, until the app is configured and an advertiser has been authorised."""
    from src.domain.ads import tiktok as T
    from src.integrations.tiktok_ads import gmv_max
    from src.integrations.tiktok_ads.client import TikTokAdsClient
    from src.integrations.tiktok_shop.auth import TokenStore

    if not settings.tiktok_ads_app_id:
        return {"skipped": "TIKTOK_ADS_APP_ID not configured"}
    tok = TokenStore(f"{settings.token_store_dir}/tiktok_ads_tokens.json").load()
    if not tok or not tok.get("access_token"):
        return {"skipped": "advertiser not authorised yet"}
    advertisers = [str(a) for a in (tok.get("advertiser_ids") or [])]
    if not advertisers:
        return {"skipped": "token carries no advertiser_ids"}

    ctx = build_context(session)
    shop = ctx.shop
    start, end = T.window(shop.timezone or "Asia/Jakarta", settings.tiktok_ads_backfill_days)
    client = TikTokAdsClient(tok["access_token"])
    rows, meta = gmv_max.fetch(client, advertisers, start, end)
    out = T.ingest(session, shop, rows, meta)
    # Per-product Cost: replaces the blended allocation, which was wrong by up to 3x per product.
    prod_rows, attributed = gmv_max.fetch_products(client, advertisers, start, end)
    out["by_product"] = T.ingest_products(session, shop, prod_rows, attributed)
    if out.get("written"):
        out.update(_compute_profit(session, shop))
    return out


def finance_cycle(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    """Hourly: orders -> statements -> profit + aggregates."""
    ctx = build_context(session)
    out = {"orders": ingest.sync_orders(ctx), "statements": ingest.sync_statements(ctx)}
    out.update(_compute_profit(session, ctx.shop))
    return out


def order_statements(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    """6h: per-order statement records (one API call per order needing a poll) + profit."""
    ctx = build_context(session)
    out = {"order_statements": ingest.sync_order_statements(ctx, unsettled_days=STATEMENT_POLL_DAYS)}
    out.update(_compute_profit(session, ctx.shop))
    return out


def withdrawals(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    ctx = build_context(session)
    return {"withdrawals": ingest.sync_withdrawals(ctx)}


def daily_metrics(session: Any, build_context: Callable[[Any], Any]) -> dict[str, Any]:
    """03:00 shop time: catalog + analytics (last METRICS_RESYNC_DAYS) then profit recompute."""
    ctx = build_context(session)
    out = {"catalog": ingest.sync_catalog(ctx),
           "metrics": ingest.sync_metrics(ctx, days=METRICS_RESYNC_DAYS)}
    out.update(_compute_profit(session, ctx.shop))
    return out


JOBS: dict[str, Callable[[Any, Callable[[Any], Any]], dict[str, Any]]] = {
    "finance_cycle": finance_cycle, "order_statements": order_statements,
    "withdrawals": withdrawals, "daily_metrics": daily_metrics, "ads_windsor": ads_windsor,
    "ads_tiktok": ads_tiktok,
}


def run_job(name: str, session_factory: Callable[[], Any], build_context: Callable[[Any], Any],
            shop_lookup: Callable[[Any], Any]) -> dict[str, Any]:
    """Runs one named job in its own session under the process lock; never raises."""
    with _LOCK:
        return _run_job(name, session_factory, build_context, shop_lookup)


def _run_job(name: str, session_factory: Callable[[], Any], build_context: Callable[[Any], Any],
             shop_lookup: Callable[[Any], Any]) -> dict[str, Any]:
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
            log.info("job %s done in %.1fs errors=%d", name,
                     (datetime.now(UTC) - started).total_seconds(), len(errors))
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
    """Sub-jobs return {"error": str} or {"errors": [..]} instead of raising -> surface in job state."""
    errs: list[str] = []
    if isinstance(out, dict):
        if isinstance(out.get("error"), str):
            errs.append(f"{path or 'job'}: {out['error'][:200]}")
        lst = out.get("errors")
        if isinstance(lst, list) and lst:
            errs.append(f"{path or 'job'}: {len(lst)} errors: {str(lst[0])[:120]}")
        for k, v in out.items():
            if k not in ("error", "errors"):
                errs += _collect_errors(v, f"{path}.{k}" if path else str(k))
    return errs


def reset_stuck_jobs(session: Any, now: datetime | None = None) -> int:
    """Worker start: job rows left "running" by a killed process -> error (interrupted)."""
    now = now or datetime.now(UTC)
    n = 0
    for r in session.scalars(select(IntegrationSyncState).where(
            IntegrationSyncState.integration == JOB_INTEGRATION,
            IntegrationSyncState.status == "running")):
        r.status, r.error = "error", f"interrupted (worker restarted {now.isoformat(timespec='seconds')})"
        n += 1
    session.commit()
    return n


def finance_due(session: Any, now: datetime | None = None,
                max_age: timedelta = timedelta(minutes=55)) -> bool:
    """Run finance_cycle immediately on start only if its last success is older than max_age."""
    now = now or datetime.now(UTC)
    r = session.scalar(select(IntegrationSyncState).where(
        IntegrationSyncState.integration == JOB_INTEGRATION,
        IntegrationSyncState.resource_type == "job:finance_cycle"))
    return r is None or r.last_successful_sync is None or now - r.last_successful_sync > max_age


def build_scheduler(runner: Callable[[str], Any], tz: str | None = None, immediate: bool = False):
    from apscheduler.executors.pool import ThreadPoolExecutor
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    tz = tz or settings.shop_timezone
    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 600}
    sched = BlockingScheduler(timezone=tz, executors={"default": ThreadPoolExecutor(1)})
    for name, slot in SLOTS.items():
        extra = {"next_run_time": datetime.now(UTC)} if immediate and name == "finance_cycle" else {}
        sched.add_job(runner, CronTrigger(timezone=tz, **slot), args=[name], id=name, **common, **extra)
    return sched
