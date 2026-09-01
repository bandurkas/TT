"""Windsor.ai GMV Max rows -> ad hierarchy, ad_metrics and shop_ad_days. See docs/windsor-ingest.md.

The one rule that matters: a date the connector does not report is left exactly as it was. Absence is
never spend of zero — reading it that way is what left 885,857 of this shop's Cost unrecorded.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.db.models import AdAccount, AdMetric, Campaign, RawApiResponse
from src.db.models_reports import ShopAdDay
from src.domain.reports import WINDSOR_SCOPE, number, record_ad_day

ZERO = Decimal(0)
RESOURCE = "gmv_max_daily"
# A rewrite this large against an existing figure is reported back, never applied silently.
DISAGREEMENT_RATIO = Decimal("0.05")


def _rows_by_day(rows: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    out: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        out[date.fromisoformat(str(r["date"]))].append(r)
    return out


def window(shop_tz: str, backfill_days: int, now: datetime | None = None) -> tuple[date, date]:
    """Rolling window ending yesterday in the shop's timezone: the connector's clock trails ours and
    rejects a future date outright, and the open day belongs to the manual form anyway."""
    today = (now or datetime.now(UTC)).astimezone(ZoneInfo(shop_tz)).date()
    end = today - timedelta(days=1)
    return end - timedelta(days=max(backfill_days, 1) - 1), end


def _ad_account(session: Any, shop: Any, rows: list[dict[str, Any]]) -> AdAccount | None:
    ext = next((str(r["account_id"]) for r in rows if r.get("account_id")), None)
    if not ext:
        return None
    acc = session.scalar(select(AdAccount).where(AdAccount.external_advertiser_id == ext))
    if acc is None:
        acc = AdAccount(shop_id=shop.id, external_advertiser_id=ext)
        session.add(acc)
    acc.name = next((r.get("account_name") for r in rows if r.get("account_name")), acc.name)
    # Windsor reports neither currency nor timezone; the shop's own are asserted (docs §3).
    acc.currency, acc.timezone = shop.currency, shop.timezone
    session.flush()
    return acc


def _campaign(session: Any, acc: AdAccount, ext_id: str, name: str | None) -> Campaign:
    c = session.scalar(select(Campaign).where(Campaign.ad_account_id == acc.id,
                                              Campaign.external_campaign_id == ext_id))
    if c is None:
        c = Campaign(ad_account_id=acc.id, external_campaign_id=ext_id)
        session.add(c)
    c.name, c.campaign_type = name or c.name, "GMV_MAX"
    session.flush()
    return c


def _metric(session: Any, campaign_id: int, day: date, spend: Decimal, currency: str,
            fetched_at: datetime, final: bool) -> None:
    m = session.scalar(select(AdMetric).where(AdMetric.entity_type == "campaign",
                                              AdMetric.entity_id == campaign_id,
                                              AdMetric.metric_date == day,
                                              AdMetric.metric_hour.is_(None)))
    if m is None:
        m = AdMetric(entity_type="campaign", entity_id=campaign_id, metric_date=day, metric_hour=None)
        session.add(m)
    # Only spend is real here: impressions/clicks/conversions come back 0, which is not a measurement.
    m.spend, m.currency, m.fetched_at, m.is_final = spend, currency, fetched_at, final
    session.flush()


def _stored_cost(session: Any, shop_id: int, day: date) -> Decimal | None:
    row = session.scalar(select(ShopAdDay).where(ShopAdDay.shop_id == shop_id,
                                                 ShopAdDay.metric_date == day))
    return number(row.cost or 0) if row is not None else None


def ingest(session: Any, shop: Any, rows: list[dict[str, Any]], meta: dict[str, Any],
           now: datetime | None = None) -> dict[str, Any]:
    """Store raw, then write only the days the connector actually reported. Commits per day."""
    fetched_at = now or datetime.now(UTC)
    session.add(RawApiResponse(integration="windsor", resource=RESOURCE, shop_id=shop.id,
                               request_meta=meta, payload={"data": rows}, fetched_at=fetched_at))
    session.commit()
    if not rows:
        return {"days": 0, "written": 0, "campaigns": 0, "disagreements": [], "note": "no rows"}

    tz = shop.timezone
    today = fetched_at.astimezone(ZoneInfo(tz)).date()
    acc = _ad_account(session, shop, rows)
    written, disagreements, campaigns = 0, [], set()
    for day, day_rows in sorted(_rows_by_day(rows).items()):
        total = sum((number(r.get("gmv_max_ads_spend") or 0) for r in day_rows), ZERO)
        final = day < today
        if acc is not None:
            for r in day_rows:
                c = _campaign(session, acc, str(r["campaign_id"]), r.get("campaign"))
                campaigns.add(c.external_campaign_id)
                _metric(session, c.id, day, number(r.get("gmv_max_ads_spend") or 0),
                        shop.currency, fetched_at, final)
            session.commit()
        before = _stored_cost(session, shop.id, day)
        if before is not None and before != total:
            base = max(before, total)
            if base > ZERO and abs(total - before) / base >= DISAGREEMENT_RATIO:
                disagreements.append({"date": str(day), "stored": str(before), "windsor": str(total)})
        try:
            res = record_ad_day(session, shop.id, day, total, None, None, fetched_at, tz,
                                final=final, note=f"Windsor.ai GMV Max, {len(day_rows)} campaign(s)",
                                entered_by="windsor", scope=WINDSOR_SCOPE, label="windsor-gmv-max")
        except ValueError as e:
            # "a newer observation exists" is normal on a re-run; nothing is overwritten.
            disagreements.append({"date": str(day), "skipped": str(e)})
            session.rollback()
            continue
        written += 0 if res.get("unchanged") else 1
    return {"days": len(_rows_by_day(rows)), "written": written, "campaigns": len(campaigns),
            "disagreements": disagreements}
