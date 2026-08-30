from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.alerts.engine import AlertConfig, AlertEngine, ShopSnapshot
from src.analytics.anomaly_detection import Anomaly, Severity
from src.analytics.creative_scoring import Classification, ClassificationResult, Confidence
from src.analytics.data_quality import DataQuality, DQState
from src.analytics.reconciliation import (
    FinanceTxn,
    Order,
    OrderItem,
    Settlement,
    reconcile,
)

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
CFG = AlertConfig(alert_cooldown=timedelta(hours=6), large_spend_threshold=Decimal(1000))
D = Decimal


def _cls(cls, spend="100", profit="50", vid="v1"):
    return ClassificationResult(vid, cls, Confidence.HIGH, ("evidence",), D("0.03"), D("0.05"),
                                D(spend), D(profit))


def _anom(metric, cur, base, delta, sev=Severity.WARNING, eid="v1"):
    return Anomaly("video", eid, metric, D(cur), D(base), D(delta), sev, (f"{metric} ev",))


def test_winner_opportunity_and_large_spend_critical():
    alerts, state = AlertEngine.evaluate(
        [], [_cls(Classification.WINNER), _cls(Classification.LOSER, "2000", "-2000", "v2")],
        None, CFG, NOW, {})
    keys = {a.dedupe_key: a.severity for a in alerts}
    assert keys == {"winner:video:v1": Severity.OPPORTUNITY,
                    "large_spend_no_profit:video:v2": Severity.CRITICAL}
    assert set(state) == set(keys) and state["winner:video:v1"] == NOW


def test_spend_up_without_orders():
    alerts, _ = AlertEngine.evaluate(
        [_anom("ad_spend", 200, 100, 100), _anom("orders", 100, 100, 0, eid="v1")],
        [], None, CFG, NOW, {})
    assert [a.dedupe_key for a in alerts] == ["spend_no_orders:video:v1"]
    assert alerts[0].severity == Severity.WARNING
    alerts, _ = AlertEngine.evaluate(
        [_anom("ad_spend", 200, 100, 100),
         _anom("orders", 180, 100, 80, Severity.OPPORTUNITY)], [], None, CFG, NOW, {})
    assert alerts == []


def test_margin_floor_and_data_stale_and_settlement_mismatch():
    dq = DataQuality(DQState.POOR, 40, ("data is 500 min old",), frozenset({"STALE"}))
    recon = reconcile([Order("a", D(100))], [OrderItem("a", D(100))],
                      [FinanceTxn("t", "a", D(90))], [Settlement("s", "a", D(80))])
    alerts, _ = AlertEngine.evaluate([], [], dq, CFG, NOW, {},
                                     shop=ShopSnapshot(net_margin=D("0.05")), reconciliation=recon)
    keys = {a.dedupe_key: a.severity for a in alerts}
    assert keys == {"margin_below_floor:shop": Severity.CRITICAL,
                    "data_stale:shop": Severity.WARNING,
                    "settlement_mismatch:shop": Severity.WARNING}
    assert any("a: diff -10" in e for a in alerts for e in a.evidence)


def test_dedupe_and_cooldown():
    cls = [_cls(Classification.WINNER), _cls(Classification.WINNER)]
    a1, s1 = AlertEngine.evaluate([], cls, None, CFG, NOW, {})
    assert len(a1) == 1
    a2, s2 = AlertEngine.evaluate([], cls, None, CFG, NOW + timedelta(hours=1), s1)
    assert a2 == [] and s2 == s1
    a3, s3 = AlertEngine.evaluate([], cls, None, CFG, NOW + timedelta(hours=6), s1)
    assert len(a3) == 1 and s3["winner:video:v1"] == NOW + timedelta(hours=6)


def test_evaluate_is_pure():
    state = {}
    AlertEngine.evaluate([], [_cls(Classification.WINNER)], None, CFG, NOW, state)
    assert state == {}
    assert AlertEngine.evaluate([], [], None, CFG, NOW, {}) == ([], {})
