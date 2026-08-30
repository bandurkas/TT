"""Pure alert engine: rules from SPEC §14 with dedupe keys and cooldowns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from src.analytics.anomaly_detection import Anomaly, Severity
from src.analytics.creative_scoring import Classification, ClassificationResult
from src.analytics.data_quality import DataQuality, DQState
from src.analytics.reconciliation import ReconciliationSummary, ReconStatus


@dataclass(frozen=True)
class Alert:
    severity: Severity
    dedupe_key: str
    title: str
    message: str
    entity_type: str
    entity_id: str
    evidence: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class AlertConfig:
    alert_cooldown: timedelta = timedelta(hours=6)
    minimum_net_margin: Decimal = Decimal("0.10")
    large_spend_threshold: Decimal = Decimal(500000)
    spend_up_min_pct: Decimal = Decimal(25)


@dataclass(frozen=True)
class ShopSnapshot:
    net_margin: Decimal | None = None
    ad_spend: Decimal | None = None
    net_profit: Decimal | None = None


State = Mapping[str, datetime]


def _spend_without_orders(anomalies: Sequence[Anomaly], cfg: AlertConfig, now: datetime
                          ) -> list[Alert]:
    by_entity: dict[tuple[str, str], dict[str, Anomaly]] = {}
    for a in anomalies:
        by_entity.setdefault((a.entity_type, a.entity_id), {})[a.metric] = a
    out = []
    for (etype, eid), metrics in by_entity.items():
        spend = metrics.get("ad_spend")
        if spend is None or spend.delta_pct is None or spend.delta_pct < cfg.spend_up_min_pct:
            continue
        orders = metrics.get("orders")
        orders_up = orders is not None and orders.delta_pct is not None and (
            orders.delta_pct >= spend.delta_pct / 2
        )
        if orders_up:
            continue
        ev = list(spend.evidence)
        ev.append(orders.evidence[0] if orders else "orders flat vs baseline")
        out.append(Alert(Severity.WARNING, f"spend_no_orders:{etype}:{eid}",
                         f"Spend up without orders: {etype} {eid}",
                         f"Ad spend +{spend.delta_pct}% while orders did not follow.",
                         etype, eid, tuple(ev), now))
    return out


def _from_classifications(cls: Sequence[ClassificationResult], cfg: AlertConfig, now: datetime
                          ) -> list[Alert]:
    out = []
    for c in cls:
        if c.classification == Classification.WINNER:
            out.append(Alert(Severity.OPPORTUNITY, f"winner:video:{c.video_id}",
                             f"Winning video detected: {c.video_id}",
                             f"Net profit {c.net_profit}, confidence {c.confidence}.",
                             "video", c.video_id, c.reasons, now))
        if c.ad_spend >= cfg.large_spend_threshold and c.net_profit <= 0:
            out.append(Alert(Severity.CRITICAL, f"large_spend_no_profit:video:{c.video_id}",
                             f"Large spend with no profit: {c.video_id}",
                             f"Spend {c.ad_spend}, net profit {c.net_profit}.",
                             "video", c.video_id, c.reasons, now))
    return out


def _shop_rules(shop: ShopSnapshot | None, cfg: AlertConfig, now: datetime) -> list[Alert]:
    if shop is None:
        return []
    out = []
    if shop.net_margin is not None and shop.net_margin < cfg.minimum_net_margin:
        out.append(Alert(Severity.CRITICAL, "margin_below_floor:shop",
                         "Shop net margin below floor",
                         f"Net margin {shop.net_margin} < floor {cfg.minimum_net_margin}.",
                         "shop", "shop", (f"net margin {shop.net_margin}",), now))
    if (shop.ad_spend is not None and shop.net_profit is not None
            and shop.ad_spend >= cfg.large_spend_threshold and shop.net_profit <= 0):
        out.append(Alert(Severity.CRITICAL, "large_spend_no_profit:shop",
                         "Large spend with zero/negative profit",
                         f"Ad spend {shop.ad_spend}, net profit {shop.net_profit}.",
                         "shop", "shop", (f"spend {shop.ad_spend}", f"profit {shop.net_profit}"),
                         now))
    return out


def _dq_rules(dq: DataQuality | None, now: datetime) -> list[Alert]:
    if dq is None:
        return []
    if "STALE" in dq.codes:
        return [Alert(Severity.WARNING, "data_stale:shop", "API data has stopped updating",
                      "; ".join(dq.reasons), "shop", "shop", dq.reasons, now)]
    if dq.state == DQState.POOR:
        return [Alert(Severity.WARNING, "data_poor:shop", "Data quality POOR",
                      "; ".join(dq.reasons), "shop", "shop", dq.reasons, now)]
    return []


def _recon_rules(recon: ReconciliationSummary | None, now: datetime) -> list[Alert]:
    if recon is None or recon.counts.get(ReconStatus.MISMATCH, 0) == 0:
        return []
    n = recon.counts[ReconStatus.MISMATCH]
    ev = tuple(f"{r.order_id}: diff {r.difference}" for r in recon.orders
               if r.status == ReconStatus.MISMATCH)[:10]
    return [Alert(Severity.WARNING, "settlement_mismatch:shop",
                  f"Settlement mismatch on {n} orders",
                  f"Total difference {recon.total_difference}.", "shop", "shop", ev, now)]


class AlertEngine:
    @staticmethod
    def evaluate(
        anomalies: Sequence[Anomaly],
        classifications: Sequence[ClassificationResult],
        dq: DataQuality | None,
        config: AlertConfig,
        now: datetime,
        state: State,
        shop: ShopSnapshot | None = None,
        reconciliation: ReconciliationSummary | None = None,
    ) -> tuple[list[Alert], dict[str, datetime]]:
        candidates = (
            _from_classifications(classifications, config, now)
            + _spend_without_orders(anomalies, config, now)
            + _shop_rules(shop, config, now)
            + _dq_rules(dq, now)
            + _recon_rules(reconciliation, now)
        )
        new_state = dict(state)
        to_send: list[Alert] = []
        seen: set[str] = set()
        for a in candidates:
            if a.dedupe_key in seen:
                continue
            seen.add(a.dedupe_key)
            last = new_state.get(a.dedupe_key)
            if last is not None and now - last < config.alert_cooldown:
                continue
            to_send.append(a)
            new_state[a.dedupe_key] = now
        return to_send, new_state
