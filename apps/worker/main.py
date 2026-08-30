"""Worker: APScheduler loop (finance hourly, statements/withdrawals 6h, metrics daily 03:00 shop tz)."""
import logging
import signal

from apps.worker import scheduler
from apps.worker.cli import build_context, shop_from_db
from src.config.settings import settings
from src.db.session import SessionLocal

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("tt.worker")


def run(name: str) -> dict:
    return scheduler.run_job(name, SessionLocal, build_context, shop_from_db)


if __name__ == "__main__":
    with SessionLocal() as s:
        stuck = scheduler.reset_stuck_jobs(s)
        immediate = scheduler.finance_due(s)
    log.info("worker up: jobs=%s tz=%s reset_stuck=%d immediate_finance=%s",
             list(scheduler.JOBS), settings.shop_timezone, stuck, immediate)
    sched = scheduler.build_scheduler(run, immediate=immediate)
    signal.signal(signal.SIGTERM, lambda *_: sched.shutdown(wait=False))
    sched.start()
