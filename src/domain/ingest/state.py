"""DB-backed SyncStateStore over integration_sync_state + pure cursor helpers."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import IntegrationSyncState
from src.integrations.sync_state import SyncState, SyncStateStore


class DbSyncStateStore(SyncStateStore):
    def __init__(self, session: Session):
        super().__init__()
        self.session = session

    def _row(self, integration: str, resource_type: str, shop_id: str) -> IntegrationSyncState | None:
        return self.session.scalar(select(IntegrationSyncState).where(
            IntegrationSyncState.integration == integration,
            IntegrationSyncState.resource_type == resource_type,
            IntegrationSyncState.shop_id == int(shop_id)))

    def get(self, integration: str, resource_type: str, shop_id: str) -> SyncState:
        r = self._row(integration, resource_type, shop_id)
        if r is None:
            return SyncState(integration, resource_type, shop_id)
        return SyncState(integration, resource_type, shop_id, cursor=r.cursor,
                         last_successful_sync=_iso(r.last_successful_sync),
                         last_attempt=_iso(r.last_attempt), status=r.status, error=r.error)

    def upsert(self, state: SyncState) -> SyncState:
        r = self._row(state.integration, state.resource_type, state.shop_id)
        if r is None:
            r = IntegrationSyncState(integration=state.integration,
                                     resource_type=state.resource_type,
                                     shop_id=int(state.shop_id))
            self.session.add(r)
        r.cursor, r.status, r.error = state.cursor, state.status, state.error
        r.last_successful_sync = _parse(state.last_successful_sync)
        r.last_attempt = _parse(state.last_attempt)
        self.session.commit()
        return state

    def all(self) -> list[SyncState]:
        rows = self.session.scalars(select(IntegrationSyncState)).all()
        return [self.get(r.integration, r.resource_type, str(r.shop_id)) for r in rows]


def _iso(d: datetime | None) -> str | None:
    return d.astimezone(UTC).isoformat(timespec="seconds") if d else None


def _parse(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


# --- cursor helpers (pure) ---------------------------------------------------------
def time_window(cursor: str | None, *, now: datetime, default_days: int,
                overlap: timedelta = timedelta(hours=1)) -> tuple[int, int]:
    """[ge, lt) unix seconds. cursor = ISO datetime of last synced update_time; re-read `overlap`
    before it to catch late updates. No cursor => now - default_days."""
    if cursor:
        start = datetime.fromisoformat(cursor) - overlap
    else:
        start = now - timedelta(days=default_days)
    return int(start.timestamp()), int(now.timestamp())


def next_cursor(prev: str | None, seen_ts: list[datetime | None]) -> str | None:
    vals = [t for t in seen_ts if t is not None]
    if prev:
        vals.append(datetime.fromisoformat(prev))
    return max(vals).astimezone(UTC).isoformat(timespec="seconds") if vals else prev


def days_to_sync(cursor: str | None, *, today_local: date, default_days: int,
                 lag_days: int = 1, resync_days: int = 3) -> list[date]:
    """Daily analytics: latest available = today - lag. Re-fetch last `resync_days` after the
    cursor (D-1 numbers may still restate). cursor = ISO date of last synced day."""
    last = today_local - timedelta(days=lag_days)
    if cursor:
        start = date.fromisoformat(cursor) - timedelta(days=resync_days - 1)
    else:
        start = last - timedelta(days=default_days - 1)
    if start > last:
        return []
    return [start + timedelta(days=i) for i in range((last - start).days + 1)]
