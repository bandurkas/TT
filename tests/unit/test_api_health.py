from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from apps.api import main as api


def _session(rows):
    s = MagicMock()
    s.__enter__.return_value = s
    s.scalars.return_value = rows
    return s


def test_health_reports_jobs_and_syncs():
    t = datetime.now(UTC) - timedelta(minutes=30)
    rows = [NS(integration="tt", resource_type="job:finance_cycle", status="success",
               last_successful_sync=t, last_attempt=t, error=None),
            NS(integration="tiktok_shop", resource_type="orders", status="error",
               last_successful_sync=None, last_attempt=t, error="boom")]
    with patch.object(api, "SessionLocal", lambda: _session(rows)):
        r = TestClient(api.app).get("/health")
    body = r.json()
    assert body["status"] == "degraded" and body["db"] == "ok"
    assert body["jobs"][0]["resource"] == "job:finance_cycle" and body["jobs"][0]["age_minutes"] == 30
    assert body["syncs"][0]["error"] == "boom" and body["syncs"][0]["last_success"] is None


def test_health_db_down():
    s = MagicMock()
    s.__enter__.side_effect = RuntimeError("no db")
    with patch.object(api, "SessionLocal", lambda: s):
        body = TestClient(api.app).get("/health").json()
    assert body["status"] == "degraded" and body["db"].startswith("error") and body["jobs"] == []
