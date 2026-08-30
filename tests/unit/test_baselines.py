from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from src.analytics.baselines import (
    DailyValue,
    Point,
    compute_baselines,
    compute_baselines_daily,
    intraday_pace,
    pct_change,
)

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _daily_points(values: list[int]) -> list[Point]:
    return [Point(NOW - timedelta(days=i, hours=1), Decimal(v)) for i, v in enumerate(values)]


def test_pct_change_basic_and_zero_safe():
    assert pct_change(Decimal(120), Decimal(100)) == Decimal("20.0")
    assert pct_change(Decimal(80), Decimal(100)) == Decimal("-20.0")
    assert pct_change(Decimal(5), Decimal(0)) is None
    assert pct_change(None, Decimal(1)) is None
    assert pct_change(Decimal(1), None) is None
    assert pct_change(Decimal(1), Decimal(3)) == Decimal("-66.7")


def test_compute_baselines_windows():
    b = compute_baselines(_daily_points([10, 20, 30, 40, 50, 60, 70, 80]), NOW)
    assert b.last_24h == Decimal(10)
    assert b.prev_comparable_24h == Decimal(20)
    assert b.avg_3d == Decimal(30)
    assert b.avg_7d == Decimal(50)
    assert b.same_weekday is None  # only 1 of 4 same-weekday buckets has data
    assert b.avg_14d is None and b.avg_30d is None
    assert b.days_with_data == 8


def test_compute_baselines_requires_full_bucket_coverage():
    pts = _daily_points([1] * 31)
    b = compute_baselines(pts, NOW)
    assert b.avg_30d == Decimal(1) and b.same_weekday == Decimal(1) and b.days_with_data == 31
    gap = [p for p in pts if p.ts.date() != (NOW - timedelta(days=2)).date()]
    b = compute_baselines(gap, NOW)
    assert b.avg_3d is None and b.avg_7d is None and b.avg_30d is None
    assert b.same_weekday == Decimal(1) and b.days_with_data == 30
    b = compute_baselines(_daily_points([5, 0, 7]), NOW)  # explicit zero point counts as data
    assert b.avg_3d is None and b.prev_comparable_24h == Decimal(0)
    b = compute_baselines(_daily_points([5]), NOW)
    assert b.prev_comparable_24h is None


def test_compute_baselines_empty_and_future_points():
    b = compute_baselines([], NOW)
    assert b.last_24h is None and b.avg_7d is None
    b = compute_baselines([Point(NOW + timedelta(hours=1), Decimal(99))], NOW)
    assert b.last_24h == Decimal(0)


def test_compute_baselines_daily_skips_missing_days():
    today = date(2026, 8, 30)
    daily = [
        DailyValue(today, Decimal(5)),
        DailyValue(today - timedelta(days=1), Decimal(10)),
        DailyValue(today - timedelta(days=3), Decimal(30)),
        DailyValue(today - timedelta(days=7), Decimal(70)),
        DailyValue(today - timedelta(days=14), Decimal(90)),
    ]
    b = compute_baselines_daily(daily, today)
    assert b.last_24h == Decimal(5)
    assert b.prev_comparable_24h == Decimal(10)
    assert b.avg_3d == Decimal(20)
    assert b.avg_7d == Decimal(110) / 3
    assert b.same_weekday == Decimal(80)
    assert compute_baselines_daily([], today).avg_30d is None


def test_intraday_pace_uses_same_weekday_cumulative():
    pts = []
    for k in range(1, 5):
        d = NOW - timedelta(days=7 * k)
        pts += [Point(d.replace(hour=9), Decimal(10)), Point(d.replace(hour=11), Decimal(5)),
                Point(d.replace(hour=18), Decimal(100))]
    pts += [Point(NOW.replace(hour=8), Decimal(6)), Point(NOW.replace(hour=13), Decimal(50))]
    pts.append(Point(NOW - timedelta(days=1), Decimal(1000)))
    pace = intraday_pace(pts, NOW)
    assert pace.samples == 4
    assert pace.expected == Decimal(15)
    assert pace.actual == Decimal(6)
    assert pace.pct == Decimal("-60.0")


def test_intraday_pace_rejects_naive_now():
    with pytest.raises(ValueError):
        intraday_pace([], NOW.replace(tzinfo=None))


def test_intraday_pace_no_history():
    pace = intraday_pace([Point(NOW - timedelta(hours=1), Decimal(3))], NOW)
    assert pace.actual == Decimal(3)
    assert pace.expected is None and pace.pct is None and pace.samples == 0
