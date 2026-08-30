"""Metric anomalies vs baseline and funnel-stage deterioration (SPEC §8.3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from src.analytics.baselines import pct_change

ZERO = Decimal(0)


class Severity(StrEnum):
    INFO = "INFO"
    OPPORTUNITY = "OPPORTUNITY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Anomaly:
    entity_type: str
    entity_id: str
    metric: str
    current: Decimal
    baseline: Decimal | None
    delta_pct: Decimal | None
    severity: Severity
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class AnomalyConfig:
    warning_pct: Decimal = Decimal(25)
    critical_pct: Decimal = Decimal(50)
    opportunity_pct: Decimal = Decimal(25)
    higher_is_better: Mapping[str, bool] = field(default_factory=lambda: {
        "orders": True, "gmv": True, "net_revenue": True, "net_profit": True,
        "net_margin": True, "ctr": True, "cvr": True, "roas": True, "aov": True,
        "ad_spend": False, "cpm": False, "cpc": False, "cpa": False, "refund_rate": False,
    })
    min_samples: Mapping[str, int] = field(default_factory=dict)


def detect_anomaly(
    entity_type: str,
    entity_id: str,
    metric: str,
    current: Decimal,
    baseline: Decimal | None,
    config: AnomalyConfig,
    sample: int | None = None,
) -> Anomaly | None:
    need = config.min_samples.get(metric)
    if need is not None and (sample is None or sample < need):
        return None
    if baseline is None:
        return None
    if baseline == 0:
        if current == 0:
            return None
        return Anomaly(entity_type, entity_id, metric, current, baseline, None, Severity.INFO,
                       (f"{metric}: {current} vs baseline 0 (no comparable history)",))
    delta = pct_change(current, baseline)
    assert delta is not None
    better = config.higher_is_better.get(metric, True)
    favorable = (delta > 0) == better
    mag = abs(delta)
    if favorable:
        if mag < config.opportunity_pct:
            return None
        sev = Severity.OPPORTUNITY
    elif mag >= config.critical_pct:
        sev = Severity.CRITICAL
    elif mag >= config.warning_pct:
        sev = Severity.WARNING
    else:
        return None
    ev = f"{metric}: {current} vs baseline {baseline} ({'+' if delta > 0 else ''}{delta}%)"
    if sample is not None:
        ev += f", sample {sample}"
    return Anomaly(entity_type, entity_id, metric, current, baseline, delta, sev, (ev,))


def detect_anomalies(
    entity_type: str,
    entity_id: str,
    current: Mapping[str, Decimal],
    baseline: Mapping[str, Decimal | None],
    config: AnomalyConfig,
    samples: Mapping[str, int] | None = None,
) -> list[Anomaly]:
    out = []
    for metric, cur in current.items():
        a = detect_anomaly(entity_type, entity_id, metric, cur, baseline.get(metric), config,
                           (samples or {}).get(metric))
        if a is not None:
            out.append(a)
    return out


@dataclass(frozen=True)
class FunnelStage:
    name: str
    count: int


@dataclass(frozen=True)
class FunnelDiagnosis:
    stage_from: str
    stage_to: str
    current_rate: Decimal
    baseline_rate: Decimal
    delta_pct: Decimal
    lost_at_stage: Decimal
    lost_orders: Decimal
    lost_profit: Decimal | None
    evidence: tuple[str, ...]


def _rates(stages: Sequence[FunnelStage]) -> list[Decimal | None]:
    return [None if a.count == 0 else Decimal(b.count) / Decimal(a.count)
            for a, b in pairwise(stages)]


def detect_funnel_deterioration(
    current: Sequence[FunnelStage],
    baseline: Sequence[FunnelStage],
    avg_profit_per_order: Decimal | None = None,
    min_stage_count: int = 30,
    order_stage: str = "order",
) -> FunnelDiagnosis | None:
    """Stage transition with the largest relative conversion drop; lost orders propagated downstream."""
    if len(current) != len(baseline) or len(current) < 2:
        return None
    if any(c.name != b.name for c, b in zip(current, baseline, strict=True)):
        return None
    cur_r, base_r = _rates(current), _rates(baseline)
    worst: tuple[int, Decimal] | None = None
    for i, (cr, br) in enumerate(zip(cur_r, base_r, strict=True)):
        if cr is None or br is None or br == 0 or current[i].count < min_stage_count:
            continue
        drop = (br - cr) / br
        if drop > 0 and (worst is None or drop > worst[1]):
            worst = (i, drop)
    if worst is None:
        return None
    i = worst[0]
    cr, br = cur_r[i], base_r[i]
    assert cr is not None and br is not None
    lost_at_stage = Decimal(current[i].count) * br - Decimal(current[i + 1].count)
    names = [s.name.lower() for s in current]
    end = names.index(order_stage.lower()) if order_stage.lower() in names else len(current) - 1
    lost_orders = lost_at_stage
    for j in range(i + 1, end):
        r = cur_r[j]
        lost_orders *= r if r is not None else ZERO
    lost_orders = lost_orders.quantize(Decimal("0.1"))
    lost_profit = None if avg_profit_per_order is None else (
        lost_orders * avg_profit_per_order).quantize(Decimal("0.01"))
    delta = pct_change(cr, br)
    assert delta is not None
    expected_next = (Decimal(current[i].count) * br).quantize(Decimal("0.1"))
    cur_pct = (cr * 100).quantize(Decimal("0.01"))
    base_pct = (br * 100).quantize(Decimal("0.01"))
    ev = [
        (f"{current[i].name} -> {current[i + 1].name}: {cur_pct}% vs baseline {base_pct}% "
         f"({delta}%)"),
        (f"{current[i].count} at {current[i].name}, {current[i + 1].count} reached "
         f"{current[i + 1].name} (expected {expected_next})"),
        f"estimated lost orders: {lost_orders}",
    ]
    if lost_profit is not None:
        ev.append(f"estimated lost profit: {lost_profit}")
    return FunnelDiagnosis(current[i].name, current[i + 1].name, cr, br, delta,
                           lost_at_stage.quantize(Decimal("0.1")), lost_orders, lost_profit,
                           tuple(ev))
