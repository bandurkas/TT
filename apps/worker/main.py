import logging
import time

logging.basicConfig(level="INFO")
log = logging.getLogger("tt.worker")

if __name__ == "__main__":
    # Placeholder until Phase 1 sync jobs exist (Celery beat / APScheduler decision pending)
    log.info("worker skeleton up; no jobs registered yet")
    while True:
        time.sleep(3600)
