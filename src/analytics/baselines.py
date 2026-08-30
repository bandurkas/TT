"""Rolling baselines and intraday pace on (timestamp, value) points or daily aggregates."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)
PCT_Q = Decimal("0.1")


@dataclass(frozen=True)
class Point:
    ts: datetime
    value: Decimal


@dataclass(frozen=True)
class DailyValue:
    day: date
    value: Decimal


@dataclass(frozen=True)
class Baselines:
    last_24h: Decimal | None
    prev_comparable_24h: Decimal | None
    avg_3d: Decimal | None
    avg_7d: Decimal | None
    avg_14d: Decimal | None
    avg_30d: Decimal | None
    same_weekday: Decimal | None
    days_with_data: int = 0  # 24h buckets (of the last 31) containing >= 1 point


@dataclass(frozen=True)
class Pace:
    actual: Decimal
    expected: Decimal | None
    pct: Decimal | None
    samples: int


def pct_change(current: Decimal | None, baseline: Decimal | None) -> Decimal | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return ((current - baseline) / abs(baseline) * 100).quantize(PCT_Q, rounding=ROUND_HALF_UP)


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, ZERO) / Decimal(len(values))


def _window_sums(
    points: Iterable[Point], now: datetime, n_windows: int
) -> tuple[list[Decimal], list[bool]]:
    sums = [ZERO] * n_windows
    has = [False] * n_windows
    for p in points:
        if p.ts > now:
            continue
        age = now - p.ts
        idx = int(age.total_seconds() // 86400)
        if age.total_seconds() % 86400 == 0 and idx > 0:
            idx -= 1
        if idx < n_windows:
            sums[idx] += p.value
            has[idx] = True
    return sums, has


def compute_baselines(points: Sequence[Point], now: datetime, same_weekday_n: int = 4) -> Baselines:
    """Windows are 24h buckets ending at `now`; empty buckets count as 0 (additive metric).
    An avg over N buckets is None unless every one of those N buckets has >= 1 point."""
    if not points:
        return Baselines(None, None, None, None, None, None, None)
    n_windows = max(31, 7 * same_weekday_n + 1)
    w, has = _window_sums(points, now, n_windows)
    sw_idx = [7 * k for k in range(1, same_weekday_n + 1)]

    def avg(idx: Sequence[int]) -> Decimal | None:
        return _mean([w[i] for i in idx]) if all(has[i] for i in idx) else None

    return Baselines(
        last_24h=w[0],
        prev_comparable_24h=w[1] if has[1] else None,
        avg_3d=avg(range(1, 4)),
        avg_7d=avg(range(1, 8)),
        avg_14d=avg(range(1, 15)),
        avg_30d=avg(range(1, 31)),
        same_weekday=avg(sw_idx),
        days_with_data=sum(has[:31]),
    )


def compute_baselines_daily(
    daily: Sequence[DailyValue], today: date, same_weekday_n: int = 4
) -> Baselines:
    """Averages cover complete days before `today`; missing days are skipped, not zero-filled."""
    by_day = {d.day: d.value for d in daily}

    def window(n: int) -> list[Decimal]:
        return [by_day[today - timedelta(days=k)] for k in range(1, n + 1)
                if today - timedelta(days=k) in by_day]

    sw = [by_day[today - timedelta(days=7 * k)] for k in range(1, same_weekday_n + 1)
          if today - timedelta(days=7 * k) in by_day]
    return Baselines(
        last_24h=by_day.get(today),
        prev_comparable_24h=by_day.get(today - timedelta(days=1)),
        avg_3d=_mean(window(3)),
        avg_7d=_mean(window(7)),
        avg_14d=_mean(window(14)),
        avg_30d=_mean(window(30)),
        same_weekday=_mean(sw),
    )


def intraday_pace(points: Sequence[Point], now: datetime, n_weekdays: int = 4) -> Pace:
    """Actual cumulative today vs mean cumulative-by-this-hour on last N same weekdays (SPEC §44.1)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = now.date()
    cutoff = now.timetz()
    actual = ZERO
    comparable: dict[date, Decimal] = {today - timedelta(days=7 * k): ZERO
                                       for k in range(1, n_weekdays + 1)}
    seen: set[date] = set()
    for p in points:
        ts = p.ts.astimezone(now.tzinfo) if now.tzinfo else p.ts
        d = ts.date()
        if d == today:
            if ts <= now:
                actual += p.value
        elif d in comparable:
            seen.add(d)
            if ts.timetz() <= cutoff:
                comparable[d] += p.value
    samples = len(seen)
    expected = _mean([comparable[d] for d in seen]) if seen else None
    return Pace(actual=actual, expected=expected, pct=pct_change(actual, expected), samples=samples)
