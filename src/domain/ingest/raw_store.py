"""raw_sink for TikTokShopClient: every response -> raw_api_responses (committed immediately,
before normalization). PII already stripped by the client's redactor."""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.db.models import RawApiResponse


class DbRawSink:
    """Commits each raw row on its own, so a later rollback in the job (normalized upserts) never
    discards raw payloads; `last_id` = id of the most recent stored response."""

    def __init__(self, session: Session, shop_id: int | None, integration: str = "tiktok_shop"):
        self.session, self.shop_id, self.integration = session, shop_id, integration
        self.last_id: int | None = None
        self.count = 0

    def __call__(self, resource: str, meta: dict[str, Any], payload: dict[str, Any]) -> None:
        row = RawApiResponse(integration=self.integration, resource=resource, shop_id=self.shop_id,
                             request_meta=meta, payload=payload, fetched_at=datetime.now(UTC))
        self.session.add(row)
        self.session.commit()
        self.last_id, self.count = row.id, self.count + 1
