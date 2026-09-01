"""Windsor.ai GMV Max rows -> ad hierarchy, ad_metrics and shop_ad_days. See docs/windsor-ingest.md.

The one rule that matters: a date the connector does not report is left exactly as it was. Absence is
never spend of zero — reading it that way is what left 885,857 of this shop's Cost unrecorded.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.db.models import AdAccount, AdMetric, Campaign, RawApiResponse
from src.db.models_reports import ShopAdDay
from src.domain.reports import WINDSOR_SCOPE, number, record_ad_day

log = logging.getLogger("tt.windsor")
ZERO = Decimal(0)
RESOURCE = "gmv_max_daily"
# A rewrite this large against an existing figure is reported back, never applied silently.
DISAGREEMENT_RATIO = Decimal("0.05")


def _by_day_campaign(rows: list[dict[str, Any]]) -> dict[date, dict[str, dict[str, Any]]]:
    """(day, campaign) -> summed spend. The connector may split a campaign-day across rows; summing
    keeps ad_metrics and the day's Cost derived from the same arithmetic."""
    out: dict[date, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        day = date.fromisoformat(str(r["date"]))
        cid = str(r["campaign_id"])
        acc = out[day].setdefault(cid, {"campaign_id": cid, "campaign": r.get("campaign"), "spend": ZERO})
        acc["spend"] += number(r["gmv_max_ads_spend"])
        acc["campaign"] = acc["campaign"] or r.get("campaign")
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


def _stored(session: Any, shop_id: int, day: date) -> ShopAdDay | None:
    return session.scalar(select(ShopAdDay).where(ShopAdDay.shop_id == shop_id,
                                                  ShopAdDay.metric_date == day))


def ingest(session: Any, shop: Any, rows: list[dict[str, Any]], meta: dict[str, Any],
           now: datetime | None = None) -> dict[str, Any]:
    """Store raw, then write only the days the connector actually reported. Commits per day."""
    fetched_at = now or datetime.now(UTC)
    session.add(RawApiResponse(integration="windsor", resource=RESOURCE, shop_id=shop.id,
                               request_meta=meta, payload={"data": rows}, fetched_at=fetched_at))
    session.commit()
    if not rows:
        return {"days": 0, "written": 0, "unchanged": 0, "campaigns": 0, "disagreements": [],
                "note": "no rows"}

    tz = shop.timezone
    today = fetched_at.astimezone(ZoneInfo(tz)).date()
    by_day = _by_day_campaign(rows)
    acc = _ad_account(session, shop, rows)
    written = unchanged = 0
    disagreements: list[dict[str, Any]] = []
    campaigns: set[str] = set()
    for day, per_campaign in sorted(by_day.items()):
        total = sum((c["spend"] for c in per_campaign.values()), ZERO)
        final = day < today
        expected_partial = (day >= today) or not final
        before = _stored(session, shop.id, day)
        if before is not None and number(before.cost or 0) == total and before.partial == expected_partial:
            # Nothing moved. Writing anyway would insert a fresh SourceReport every hour (observed_at
            # is inside the content hash) and trigger a full profit recompute for no reason.
            unchanged += 1
            continue
        if acc is not None:
            for c in per_campaign.values():
                camp = _campaign(session, acc, c["campaign_id"], c["campaign"])
                campaigns.add(camp.external_campaign_id)
                _metric(session, camp.id, day, c["spend"], shop.currency, fetched_at, final)
            session.commit()
        if before is not None:
            was = number(before.cost or 0)
            base = max(was, total)
            if was != total and base > ZERO and abs(total - was) / base >= DISAGREEMENT_RATIO:
                d = {"date": str(day), "stored": str(was), "windsor": str(total)}
                disagreements.append(d)
                log.warning("windsor: %s restates Cost %s -> %s", day, was, total)
        try:
            res = record_ad_day(session, shop.id, day, total, None, None, fetched_at, tz,
                                final=final, note=f"Windsor.ai GMV Max, {len(per_campaign)} campaign(s)",
                                entered_by="windsor", scope=WINDSOR_SCOPE, label="windsor-gmv-max")
        except ValueError as e:
            if "newer or equal observation" not in str(e):
                raise      # a real validation failure must fail the job, not read as "skipped"
            session.rollback()
            unchanged += 1
            log.info("windsor: %s already has a newer observation; left alone", day)
            continue
        if res.get("unchanged"):
            unchanged += 1
        else:
            written += 1
    return {"days": len(by_day), "written": written, "unchanged": unchanged,
            "campaigns": len(campaigns), "disagreements": disagreements}
