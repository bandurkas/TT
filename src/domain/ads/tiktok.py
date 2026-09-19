"""TikTok Ads GMV Max rows -> ad hierarchy, ad_metrics and shop_ad_days.

Same contract as the Windsor ingest it supersedes (docs/windsor-ingest.md), with one deliberate
difference: this source reports the day in progress, so the open day is written as `partial` with the
fetch time as its observation. `partial` is what the dashboard reads to say "as of HH:MM" instead of
presenting a mid-day reading as the day's Cost.

Ad-attributed `orders` / `gross_revenue` are kept on `ad_metrics` only. They are the platform's own
attribution and are not the shop's (SPEC §7), so they never touch a ShopAdDay's figures.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from src.db.models import AdAccount, AdMetric, Campaign, RawApiResponse
from src.db.models_reports import ShopAdDay
from src.domain.reports import TIKTOK_SCOPE, number, record_ad_day

log = logging.getLogger("tt.ads.tiktok")
ZERO = Decimal(0)
RESOURCE = "gmv_max_daily"
DISAGREEMENT_RATIO = Decimal("0.05")


def window(shop_tz: str, backfill_days: int, now: datetime | None = None) -> tuple[date, date]:
    """Ends **today** in the shop's timezone — the whole point of this source over Windsor."""
    today = (now or datetime.now(UTC)).astimezone(ZoneInfo(shop_tz)).date()
    return today - timedelta(days=max(backfill_days, 1) - 1), today


def by_day(rows: list[dict[str, Any]]) -> dict[date, dict[str, dict[str, Any]]]:
    """(day, campaign) -> summed cost. Campaigns from both advertisers land in the same day."""
    out: dict[date, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        day, cid = r["date"], str(r["campaign_id"])
        acc = out[day].setdefault(cid, {"campaign_id": cid, "campaign": r.get("campaign"),
                                        "advertiser_id": r.get("advertiser_id"), "cost": ZERO,
                                        "ad_orders": 0, "ad_revenue": ZERO})
        acc["cost"] += r["cost"]
        acc["ad_orders"] += int(r.get("ad_orders") or 0)
        acc["ad_revenue"] += r.get("ad_revenue") or ZERO
        acc["campaign"] = acc["campaign"] or r.get("campaign")
    return out


def _account(session: Any, shop: Any, ext: str) -> AdAccount:
    acc = session.scalar(select(AdAccount).where(AdAccount.external_advertiser_id == ext))
    if acc is None:
        acc = AdAccount(shop_id=shop.id, external_advertiser_id=ext)
        session.add(acc)
    acc.currency, acc.timezone = shop.currency, shop.timezone
    session.commit()   # see windsor._ad_account: a later rollback must not orphan the foreign key
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


def _metric(session: Any, campaign_id: int, day: date, row: dict[str, Any], currency: str,
            fetched_at: datetime, final: bool, entity: str = "campaign") -> None:
    m = session.scalar(select(AdMetric).where(AdMetric.entity_type == entity,
                                              AdMetric.entity_id == campaign_id,
                                              AdMetric.metric_date == day,
                                              AdMetric.metric_hour.is_(None)))
    if m is None:
        m = AdMetric(entity_type=entity, entity_id=campaign_id, metric_date=day, metric_hour=None)
        session.add(m)
    m.spend, m.currency, m.fetched_at, m.is_final = row["cost"], currency, fetched_at, final
    # Platform attribution, kept apart from the shop's own orders. impressions/clicks are not part
    # of the GMV Max report at all, so they are left untouched rather than written as zero.
    m.attributed_orders, m.attributed_gmv = row["ad_orders"], row["ad_revenue"]
    session.flush()


def _stored(session: Any, shop_id: int, day: date) -> ShopAdDay | None:
    return session.scalar(select(ShopAdDay).where(ShopAdDay.shop_id == shop_id,
                                                  ShopAdDay.metric_date == day))


def _absent_spend(session: Any, shop_id: int, day: date, present: set[str]) -> Decimal:
    """Last known spend of campaigns on file for `day` that the report no longer returns."""
    q = (select(func.sum(AdMetric.spend))
         .join(Campaign, Campaign.id == AdMetric.entity_id)
         .join(AdAccount, AdAccount.id == Campaign.ad_account_id)
         .where(AdAccount.shop_id == shop_id, AdMetric.entity_type == "campaign",
                AdMetric.metric_date == day, AdMetric.metric_hour.is_(None)))
    if present:
        q = q.where(Campaign.external_campaign_id.notin_(present))
    return Decimal(str(session.scalar(q) or 0))


def ingest(session: Any, shop: Any, rows: list[dict[str, Any]], meta: dict[str, Any],
           now: datetime | None = None) -> dict[str, Any]:
    """Store raw, then write every day the report covered. Commits per day."""
    fetched_at = now or datetime.now(UTC)
    session.add(RawApiResponse(integration="tiktok_ads", resource=RESOURCE, shop_id=shop.id,
                               request_meta=meta, payload={"data": len(rows)}, fetched_at=fetched_at))
    session.commit()
    if not rows:
        return {"days": 0, "written": 0, "unchanged": 0, "campaigns": 0, "disagreements": [],
                "note": "no rows"}

    tz = shop.timezone
    today = fetched_at.astimezone(ZoneInfo(tz)).date()
    days = by_day(rows)
    accounts: dict[str, AdAccount] = {}
    written = unchanged = 0
    disagreements: list[dict[str, Any]] = []
    campaigns: set[str] = set()
    rejections: list[str] = []

    for day, per_campaign in sorted(days.items()):
        # A deleted campaign vanishes from the report, past days included. Its money was still
        # spent: absence is not zero. Found 2026-09-19, after three deletions rewrote closed days
        # down by 638,574 (13 Sept read 224 against a real 449,689).
        absent = _absent_spend(session, shop.id, day, set(per_campaign))
        total = sum((c["cost"] for c in per_campaign.values()), ZERO) + absent
        final = day < today
        before = _stored(session, shop.id, day)
        # A figure that has not moved is not rewritten: at a 15-minute cadence that would insert a
        # SourceReport every run (observed_at is inside the content hash) and force a profit recompute.
        if before is not None and number(before.cost or 0) == total \
                and before.partial == (not final) and not before.manual:
            unchanged += 1
        else:
            if before is not None and not before.manual:
                was = number(before.cost or 0)
                base = max(was, total)
                if was != total and base > ZERO and abs(total - was) / base >= DISAGREEMENT_RATIO:
                    disagreements.append({"date": str(day), "stored": str(was), "tiktok": str(total)})
            try:
                record_ad_day(session, shop.id, day, total, None, None, fetched_at, tz,
                              final=final,
                              note=(f"TikTok Ads GMV Max API, {len(per_campaign)} campaign(s)"
                                    + (f"; +{absent} kept from campaigns since deleted" if absent else "")),
                              entered_by="tiktok_ads", scope=TIKTOK_SCOPE, label="tiktok-gmv-max")
                written += 1
            except ValueError as e:
                session.rollback()
                if "newer or equal observation" in str(e):
                    unchanged += 1
                else:
                    rejections.append(f"{day}: {e}")
                    continue
        for cid, row in per_campaign.items():
            adv = str(row.get("advertiser_id") or "")
            if adv and adv not in accounts:
                accounts[adv] = _account(session, shop, adv)
            acc = accounts.get(adv)
            if acc is None:
                continue
            camp = _campaign(session, acc, cid, row.get("campaign"))
            _metric(session, camp.id, day, row, shop.currency, fetched_at, final)
            campaigns.add(cid)
        session.commit()

    return {"days": len(days), "written": written, "unchanged": unchanged,
            "campaigns": len(campaigns), "disagreements": disagreements,
            "rejections": rejections, "as_of": fetched_at.isoformat()}


def ingest_products(session: Any, shop: Any, rows: list[dict[str, Any]], attributed: Decimal,
                    now: datetime | None = None) -> dict[str, Any]:
    """Per-product Cost into ad_metrics(entity_type="product"). Replaces the blended allocation,
    which was measured wrong by up to 3x per product on 2026-09-09.

    Spend on a product the shop does not know is counted, never invented: no Product row is created
    from an ad report, and the total is reported so the money is not lost from view.
    """
    from src.db.models import Product

    fetched_at = now or datetime.now(UTC)
    tz = shop.timezone
    today = fetched_at.astimezone(ZoneInfo(tz)).date()
    ids = {str(p.external_product_id): p.id for p in
           session.scalars(select(Product).where(Product.shop_id == shop.id))}

    per: dict[tuple[int, date], dict[str, Any]] = {}
    unknown: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        pid = ids.get(r["external_product_id"])
        if pid is None:
            unknown[r["external_product_id"]] += r["cost"]
            continue
        acc = per.setdefault((pid, r["date"]), {"cost": ZERO, "ad_orders": 0, "ad_revenue": ZERO})
        acc["cost"] += r["cost"]
        acc["ad_orders"] += int(r.get("ad_orders") or 0)
        acc["ad_revenue"] += r.get("ad_revenue") or ZERO

    for (pid, day), v in per.items():
        _metric(session, pid, day, v, shop.currency, fetched_at, day < today, entity="product")
    session.commit()
    return {"products": len({p for p, _ in per}), "rows": len(per),
            "attributed_cost": str(attributed),
            "unknown_products": {k: str(v) for k, v in unknown.items()}}
