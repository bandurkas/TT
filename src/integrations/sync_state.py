"""integration_sync_state (SPEC §26): idempotent per (integration, resource_type, shop_id)."""
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Status = Literal["idle", "running", "success", "error"]
Key = tuple[str, str, str]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SyncState:
    integration: str
    resource_type: str
    shop_id: str
    cursor: str | None = None
    last_successful_sync: str | None = None
    last_attempt: str | None = None
    status: Status = "idle"
    error: str | None = None

    @property
    def key(self) -> Key:
        return (self.integration, self.resource_type, self.shop_id)


class SyncStateStore:
    def __init__(self) -> None:
        self._rows: dict[Key, SyncState] = {}

    def get(self, integration: str, resource_type: str, shop_id: str) -> SyncState:
        key = (integration, resource_type, shop_id)
        if key not in self._rows:
            self._rows[key] = SyncState(*key)
        return self._rows[key]

    def upsert(self, state: SyncState) -> SyncState:
        self._rows[state.key] = state
        self._persist()
        return state

    def start_attempt(self, integration: str, resource_type: str, shop_id: str) -> SyncState:
        s = self.get(integration, resource_type, shop_id)
        return self.upsert(replace(s, status="running", last_attempt=_now()))

    def mark_success(self, integration: str, resource_type: str, shop_id: str,
                     cursor: str | None) -> SyncState:
        s = self.get(integration, resource_type, shop_id)
        return self.upsert(replace(s, status="success", cursor=cursor,
                                   last_successful_sync=_now(), error=None))

    def mark_error(self, integration: str, resource_type: str, shop_id: str,
                   error: str) -> SyncState:
        s = self.get(integration, resource_type, shop_id)
        return self.upsert(replace(s, status="error", error=error[:2000]))

    def all(self) -> list[SyncState]:
        return list(self._rows.values())

    def _persist(self) -> None:
        pass


class JsonFileSyncStateStore(SyncStateStore):
    def __init__(self, path: str | Path):
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            for row in json.loads(self.path.read_text()):
                s = SyncState(**row)
                self._rows[s.key] = s

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(s) for s in self._rows.values()], indent=2))
        tmp.replace(self.path)
