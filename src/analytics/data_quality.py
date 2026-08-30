"""Data-quality state and confidence capping (SPEC §18)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from src.analytics.common import Confidence


class DQState(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    POOR = "POOR"


@dataclass(frozen=True)
class DataQualityInputs:
    freshness_minutes: int | None = None
    missing_hours: int = 0
    unmapped_skus: int = 0
    unmapped_creatives: int = 0
    orders_missing_cogs: int = 0
    total_orders: int = 0
    settlement_coverage_pct: Decimal | None = None
    negative_values: int = 0
    duplicate_transactions: int = 0
    currency_mismatches: int = 0


@dataclass(frozen=True)
class DataQualityConfig:
    fresh_minutes: int = 120
    stale_minutes: int = 360
    partial_score: int = 85
    poor_score: int = 50
    settlement_full_pct: Decimal = Decimal(95)
    settlement_poor_pct: Decimal = Decimal(50)
    cogs_missing_poor_pct: Decimal = Decimal(30)


@dataclass(frozen=True)
class DataQuality:
    state: DQState
    score: int
    reasons: tuple[str, ...]
    codes: frozenset[str] = frozenset()


def compute_data_quality(
    inp: DataQualityInputs, cfg: DataQualityConfig | None = None
) -> DataQuality:
    cfg = cfg or DataQualityConfig()
    score = 100
    reasons: list[str] = []
    codes: set[str] = set()
    force_poor = False

    if inp.freshness_minutes is None:
        score -= 40
        codes.add("STALE")
        reasons.append("no successful sync recorded")
        force_poor = True
    elif inp.freshness_minutes > cfg.stale_minutes:
        score -= 40
        codes.add("STALE")
        reasons.append(f"data is {inp.freshness_minutes} min old (stale > {cfg.stale_minutes})")
        force_poor = True
    elif inp.freshness_minutes > cfg.fresh_minutes:
        score -= 15
        codes.add("DELAYED")
        reasons.append(f"data is {inp.freshness_minutes} min old (> {cfg.fresh_minutes})")

    if inp.missing_hours > 0:
        score -= min(30, 5 * inp.missing_hours)
        codes.add("MISSING_HOURS")
        reasons.append(f"{inp.missing_hours} hourly buckets missing")

    if inp.unmapped_skus > 0:
        score -= min(15, 3 * inp.unmapped_skus)
        codes.add("UNMAPPED_SKU")
        reasons.append(f"{inp.unmapped_skus} SKUs unmapped (COGS unknown)")

    if inp.unmapped_creatives > 0:
        score -= min(10, 2 * inp.unmapped_creatives)
        codes.add("UNMAPPED_CREATIVE")
        reasons.append(f"{inp.unmapped_creatives} creatives unmapped (attribution uncertain)")

    if inp.orders_missing_cogs > 0 and inp.total_orders > 0:
        pct = Decimal(inp.orders_missing_cogs) * 100 / Decimal(inp.total_orders)
        score -= min(30, int(pct))
        codes.add("MISSING_COGS")
        reasons.append(f"{pct.quantize(Decimal('0.1'))}% of orders lack COGS; profit estimated")
        if pct >= cfg.cogs_missing_poor_pct:
            force_poor = True

    if inp.settlement_coverage_pct is not None and inp.settlement_coverage_pct < cfg.settlement_full_pct:
        gap = Decimal(100) - inp.settlement_coverage_pct
        score -= min(30, int(gap))
        codes.add("MISSING_SETTLEMENT")
        reasons.append(f"{gap.quantize(Decimal('0.1'))}% of orders lack final settlement; "
                       "profit shown as estimated")
        if inp.settlement_coverage_pct < cfg.settlement_poor_pct:
            codes.add("SETTLEMENT_POOR")

    if inp.negative_values > 0:
        score -= min(20, 5 * inp.negative_values)
        codes.add("NEGATIVE_VALUES")
        reasons.append(f"{inp.negative_values} unexpected negative values")

    if inp.duplicate_transactions > 0:
        score -= min(20, 5 * inp.duplicate_transactions)
        codes.add("DUPLICATES")
        reasons.append(f"{inp.duplicate_transactions} duplicate transactions")

    if inp.currency_mismatches > 0:
        score -= min(20, 10 * inp.currency_mismatches)
        codes.add("CURRENCY_MISMATCH")
        reasons.append(f"{inp.currency_mismatches} currency mismatches")

    score = max(0, min(100, score))
    if force_poor or score < cfg.poor_score:
        state = DQState.POOR
    elif score < cfg.partial_score:
        state = DQState.PARTIAL
    else:
        state = DQState.OK
    return DataQuality(state, score, tuple(reasons), frozenset(codes))


_CAP = {DQState.OK: Confidence.HIGH, DQState.PARTIAL: Confidence.MEDIUM, DQState.POOR: Confidence.LOW}
_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def confidence_cap(dq: DataQuality) -> Confidence:
    return _CAP[dq.state]


def apply_confidence_cap(confidence: Confidence, dq: DataQuality) -> Confidence:
    cap = confidence_cap(dq)
    return confidence if _RANK[confidence] <= _RANK[cap] else cap


__all__ = [
    "Confidence",
    "DQState",
    "DataQuality",
    "DataQualityConfig",
    "DataQualityInputs",
    "apply_confidence_cap",
    "compute_data_quality",
    "confidence_cap",
]
