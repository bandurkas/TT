"""Pure alert engine: rules from SPEC §14 with dedupe keys, cooldowns and fingerprints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from src.analytics.anomaly_detection import Anomaly, Severity
from src.analytics.baselines import pct_change
from src.analytics.common import Confidence
from src.analytics.creative_scoring import Classification, ClassificationResult
from src.analytics.data_quality import DataQuality, DQState, apply_confidence_cap
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
    confidence: Confidence | None = None
    key_metric: Decimal | None = None

    @property
    def fingerprint(self) -> str:
        km = "-" if self.key_metric is None else format(self.key_metric, ".2g")
        return f"{self.severity}:{km}"


@dataclass(frozen=True)
class AlertConfig:
    alert_cooldown: timedelta = timedelta(hours=6)
    minimum_net_margin: Decimal = Decimal("0.10")
    large_spend_threshold: Decimal = Decimal(500000)  # absolute fallback
    large_spend_median_multiple: Decimal | None = None  # x shop 7d median video spend
    spend_up_min_pct: Decimal = Decimal(25)


@dataclass(frozen=True)
class ShopSnapshot:
    net_margin: Decimal | None = None
    ad_spend: Decimal | None = None
    net_profit: Decimal | None = None
    median_video_spend_7d: Decimal | None = None


@dataclass(frozen=True)
class SentRecord:
    at: datetime
    fingerprint: str


State = Mapping[str, "SentRecord | datetime"]
# (entity_type, entity_id) -> metric -> (current, baseline)
MetricDeltas = Mapping[tuple[str, str], Mapping[str, tuple[Decimal, Decimal | None]]]


def _cap(conf: Confidence, dq: DataQuality | None) -> Confidence:
    return conf if dq is None else apply_confidence_cap(conf, dq)


def _large_spend_threshold(cfg: AlertConfig, shop: ShopSnapshot | None) -> Decimal:
    med = shop.median_video_spend_7d if shop else None
    if cfg.large_spend_median_multiple is not None and med is not None and med > 0:
        return med * cfg.large_spend_median_multiple
    return cfg.large_spend_threshold


def _spend_without_orders(anomalies: Sequence[Anomaly], cfg: AlertConfig, now: datetime,
                          deltas: MetricDeltas | None, dq: DataQuality | None) -> list[Alert]:
    by_entity: dict[tuple[str, str], dict[str, Anomaly]] = {}
    for a in anomalies:
        by_entity.setdefault((a.entity_type, a.entity_id), {})[a.metric] = a
    out = []
    for (etype, eid), metrics in by_entity.items():
        spend = metrics.get("ad_spend")
        if spend is None or spend.delta_pct is None or spend.delta_pct < cfg.spend_up_min_pct:
            continue
        orders = metrics.get("orders")
        raw = (deltas or {}).get((etype, eid), {}).get("orders")
        if raw is None and orders is not None:
            raw = (orders.current, orders.baseline)
        if raw is None:
            if spend.severity != Severity.CRITICAL:
                continue  # orders unknown: only a critical spend jump is worth a warning
            orders_ev, conf = "orders unknown", Confidence.LOW
        else:
            cur, base = raw
            orders_delta = pct_change(cur, base)
            if orders_delta is None:
                if cur > 0:
                    continue  # from zero baseline: orders did follow
                orders_delta = Decimal(0)
            if orders_delta >= spend.delta_pct / 2:
                continue
            orders_ev, conf = f"orders {cur} vs baseline {base} ({orders_delta}%)", Confidence.HIGH
        ev = (*spend.evidence, orders_ev)
        out.append(Alert(Severity.WARNING, f"spend_no_orders:{etype}:{eid}",
                         f"Spend up without orders: {etype} {eid}",
                         f"Ad spend +{spend.delta_pct}% while orders did not follow.",
                         etype, eid, ev, now, _cap(conf, dq), spend.delta_pct))
    return out


def _from_classifications(cls: Sequence[ClassificationResult], cfg: AlertConfig, now: datetime,
                          dq: DataQuality | None, shop: ShopSnapshot | None) -> list[Alert]:
    out = []
    threshold = _large_spend_threshold(cfg, shop)
    for c in cls:
        conf = _cap(c.confidence, dq)
        weak = c.classification == Classification.INSUFFICIENT_DATA or conf is Confidence.LOW
        if c.classification == Classification.WINNER:
            out.append(Alert(Severity.OPPORTUNITY, f"winner:video:{c.video_id}",
                             f"Winning video detected: {c.video_id}",
                             f"Net profit {c.net_profit}, confidence {conf}.",
                             "video", c.video_id, c.reasons, now, conf, c.net_profit))
        if c.ad_spend >= threshold and c.net_profit <= 0:
            sev = Severity.INFO if weak else Severity.CRITICAL  # weak evidence: never CRITICAL
            out.append(Alert(sev, f"large_spend_no_profit:video:{c.video_id}",
                             f"Large spend with no profit: {c.video_id}",
                             f"Spend {c.ad_spend}, net profit {c.net_profit}.",
                             "video", c.video_id, c.reasons, now, conf, c.net_profit))
    return out


def _shop_rules(shop: ShopSnapshot | None, cfg: AlertConfig, now: datetime, sid: str,
                dq: DataQuality | None) -> list[Alert]:
    if shop is None:
        return []
    out = []
    conf = _cap(Confidence.HIGH, dq)
    if shop.net_margin is not None and shop.net_margin < cfg.minimum_net_margin:
        out.append(Alert(Severity.CRITICAL, f"margin_below_floor:shop:{sid}",
                         "Shop net margin below floor",
                         f"Net margin {shop.net_margin} < floor {cfg.minimum_net_margin}.",
                         "shop", sid, (f"net margin {shop.net_margin}",), now, conf,
                         shop.net_margin))
    if (shop.ad_spend is not None and shop.net_profit is not None
            and shop.ad_spend >= cfg.large_spend_threshold and shop.net_profit <= 0):
        out.append(Alert(Severity.CRITICAL, f"large_spend_no_profit:shop:{sid}",
                         "Large spend with zero/negative profit",
                         f"Ad spend {shop.ad_spend}, net profit {shop.net_profit}.",
                         "shop", sid, (f"spend {shop.ad_spend}", f"profit {shop.net_profit}"),
                         now, conf, shop.net_profit))
    return out


def _dq_rules(dq: DataQuality | None, now: datetime, sid: str) -> list[Alert]:
    if dq is None:
        return []
    if "STALE" in dq.codes:
        return [Alert(Severity.WARNING, f"data_stale:shop:{sid}", "API data has stopped updating",
                      "; ".join(dq.reasons), "shop", sid, dq.reasons, now, None,
                      Decimal(dq.score))]
    if dq.state == DQState.POOR:
        return [Alert(Severity.WARNING, f"data_poor:shop:{sid}", "Data quality POOR",
                      "; ".join(dq.reasons), "shop", sid, dq.reasons, now, None,
                      Decimal(dq.score))]
    return []


def _recon_rules(recon: ReconciliationSummary | None, now: datetime, sid: str) -> list[Alert]:
    if recon is None or recon.counts.get(ReconStatus.MISMATCH, 0) == 0:
        return []
    n = recon.counts[ReconStatus.MISMATCH]
    ev = tuple(f"{r.order_id}: diff {r.difference}" for r in recon.orders
               if r.status == ReconStatus.MISMATCH)[:10]
    return [Alert(Severity.WARNING, f"settlement_mismatch:shop:{sid}",
                  f"Settlement mismatch on {n} orders",
                  f"Total difference {recon.total_difference}.", "shop", sid, ev, now,
                  Confidence.HIGH, recon.total_difference)]


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
        shop_id: str = "shop",
        metric_deltas: MetricDeltas | None = None,
    ) -> tuple[list[Alert], dict[str, SentRecord]]:
        """Dedupe within a run; suppress during cooldown; after cooldown re-send only when the
        fingerprint (severity + rounded key metric) changed. Legacy datetime state is accepted."""
        candidates = (
            _from_classifications(classifications, config, now, dq, shop)
            + _spend_without_orders(anomalies, config, now, metric_deltas, dq)
            + _shop_rules(shop, config, now, shop_id, dq)
            + _dq_rules(dq, now, shop_id)
            + _recon_rules(reconciliation, now, shop_id)
        )
        new_state: dict[str, SentRecord] = {
            k: v if isinstance(v, SentRecord) else SentRecord(v, "") for k, v in state.items()
        }
        to_send: list[Alert] = []
        seen: set[str] = set()
        for a in candidates:
            if a.dedupe_key in seen:
                continue
            seen.add(a.dedupe_key)
            last = new_state.get(a.dedupe_key)
            if last is not None:
                if now - last.at < config.alert_cooldown:
                    continue
                if last.fingerprint == a.fingerprint:
                    continue
            to_send.append(a)
            new_state[a.dedupe_key] = SentRecord(now, a.fingerprint)
        return to_send, new_state
