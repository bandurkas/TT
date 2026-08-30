"""Worker: APScheduler loop (finance hourly, withdrawals 6h, metrics daily 03:00 shop time)."""
import logging

from apps.worker import scheduler
from apps.worker.cli import build_context, shop_from_db
from src.config.settings import settings
from src.db.session import SessionLocal

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("tt.worker")


def run(name: str) -> dict:
    return scheduler.run_job(name, SessionLocal, build_context, shop_from_db)


if __name__ == "__main__":
    log.info("worker up: jobs=%s tz=%s", list(scheduler.JOBS), settings.shop_timezone)
    scheduler.build_scheduler(run).start()
