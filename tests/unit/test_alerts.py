from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.alerts.engine import AlertConfig, AlertEngine, SentRecord, ShopSnapshot
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


def _cls(cls, spend="100", profit="50", vid="v1", conf=Confidence.HIGH):
    return ClassificationResult(vid, cls, conf, ("evidence",), D("0.03"), D("0.05"),
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
    assert set(state) == set(keys) and state["winner:video:v1"].at == NOW
    assert all(a.confidence == Confidence.HIGH for a in alerts)


def test_confidence_capped_by_dq_and_weak_evidence_downgrades_critical():
    dq = DataQuality(DQState.POOR, 40, ("bad",), frozenset())
    alerts, _ = AlertEngine.evaluate(
        [], [_cls(Classification.LOSER, "2000", "-2000", "v2")], dq, CFG, NOW, {})
    assert alerts[0].severity == Severity.INFO and alerts[0].confidence == Confidence.LOW
    alerts, _ = AlertEngine.evaluate(
        [], [_cls(Classification.INSUFFICIENT_DATA, "2000", "-2000", "v2")], None, CFG, NOW, {})
    assert alerts[0].severity == Severity.INFO
    alerts, _ = AlertEngine.evaluate(
        [], [_cls(Classification.LOSER, "2000", "-2000", "v2", Confidence.LOW)], None, CFG, NOW, {})
    assert alerts[0].severity == Severity.INFO
    dq_ok = DataQuality(DQState.PARTIAL, 80, (), frozenset())
    alerts, _ = AlertEngine.evaluate(
        [], [_cls(Classification.LOSER, "2000", "-2000", "v2")], dq_ok, CFG, NOW, {})
    assert alerts[0].severity == Severity.CRITICAL and alerts[0].confidence == Confidence.MEDIUM


def test_large_spend_relative_threshold_with_absolute_fallback():
    cfg = AlertConfig(large_spend_threshold=D(1000), large_spend_median_multiple=D(3))
    cls = [_cls(Classification.LOSER, "1500", "-10", "v2")]
    shop = ShopSnapshot(median_video_spend_7d=D(1000))  # threshold 3000
    assert AlertEngine.evaluate([], cls, None, cfg, NOW, {}, shop=shop)[0] == []
    shop = ShopSnapshot(median_video_spend_7d=D(400))  # threshold 1200
    assert len(AlertEngine.evaluate([], cls, None, cfg, NOW, {}, shop=shop)[0]) == 1
    assert len(AlertEngine.evaluate([], cls, None, cfg, NOW, {})[0]) == 1  # absolute 1000


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


def test_spend_up_with_proportional_orders_uses_raw_deltas():
    spend = _anom("ad_spend", 200, 100, 100)  # orders +60%: not anomalous, but followed
    deltas = {("video", "v1"): {"orders": (D(160), D(100))}}
    alerts, _ = AlertEngine.evaluate([spend], [], None, CFG, NOW, {}, metric_deltas=deltas)
    assert alerts == []
    deltas = {("video", "v1"): {"orders": (D(110), D(100))}}
    alerts, _ = AlertEngine.evaluate([spend], [], None, CFG, NOW, {}, metric_deltas=deltas)
    assert [a.dedupe_key for a in alerts] == ["spend_no_orders:video:v1"]
    assert alerts[0].confidence == Confidence.HIGH
    assert any("orders 110 vs baseline 100 (10.0%)" in e for e in alerts[0].evidence)


def test_spend_up_orders_unknown_requires_critical():
    warn = _anom("ad_spend", 130, 100, 30, Severity.WARNING)
    assert AlertEngine.evaluate([warn], [], None, CFG, NOW, {})[0] == []
    crit = _anom("ad_spend", 200, 100, 100, Severity.CRITICAL)
    alerts, _ = AlertEngine.evaluate([crit], [], None, CFG, NOW, {})
    assert len(alerts) == 1 and alerts[0].confidence == Confidence.LOW
    assert "orders unknown" in alerts[0].evidence


def test_margin_floor_and_data_stale_and_settlement_mismatch():
    dq = DataQuality(DQState.POOR, 40, ("data is 500 min old",), frozenset({"STALE"}))
    recon = reconcile([Order("a", D(100))], [OrderItem("a", D(100))],
                      [FinanceTxn("t", "a", D(90))], [Settlement("s", "a", D(80))])
    alerts, _ = AlertEngine.evaluate([], [], dq, CFG, NOW, {},
                                     shop=ShopSnapshot(net_margin=D("0.05")), reconciliation=recon,
                                     shop_id="7001")
    keys = {a.dedupe_key: a.severity for a in alerts}
    assert keys == {"margin_below_floor:shop:7001": Severity.CRITICAL,
                    "data_stale:shop:7001": Severity.WARNING,
                    "settlement_mismatch:shop:7001": Severity.WARNING}
    assert any("a: diff -10" in e for a in alerts for e in a.evidence)
    assert all(a.entity_id == "7001" for a in alerts)


def test_dedupe_and_cooldown():
    cls = [_cls(Classification.WINNER), _cls(Classification.WINNER)]
    a1, s1 = AlertEngine.evaluate([], cls, None, CFG, NOW, {})
    assert len(a1) == 1
    a2, s2 = AlertEngine.evaluate([], cls, None, CFG, NOW + timedelta(hours=1), s1)
    assert a2 == [] and s2 == s1
    # cooldown over but same fingerprint -> not re-sent
    a3, s3 = AlertEngine.evaluate([], cls, None, CFG, NOW + timedelta(hours=6), s1)
    assert a3 == [] and s3 == s1
    # cooldown over and key metric changed -> re-sent with new record
    changed = [_cls(Classification.WINNER, profit="500")]
    a4, s4 = AlertEngine.evaluate([], changed, None, CFG, NOW + timedelta(hours=6), s1)
    assert len(a4) == 1 and s4["winner:video:v1"] == SentRecord(NOW + timedelta(hours=6),
                                                                 "OPPORTUNITY:5.0e+2")
    # severity change alone also changes the fingerprint
    assert a4[0].fingerprint != a1[0].fingerprint


def test_legacy_datetime_state_accepted():
    cls = [_cls(Classification.WINNER)]
    alerts, state = AlertEngine.evaluate([], cls, None, CFG, NOW, {"winner:video:v1": NOW})
    assert alerts == [] and state["winner:video:v1"] == SentRecord(NOW, "")
    alerts, _ = AlertEngine.evaluate([], cls, None, CFG, NOW + timedelta(hours=7),
                                     {"winner:video:v1": NOW})
    assert len(alerts) == 1  # empty legacy fingerprint never matches


def test_evaluate_is_pure():
    state = {}
    AlertEngine.evaluate([], [_cls(Classification.WINNER)], None, CFG, NOW, state)
    assert state == {}
    assert AlertEngine.evaluate([], [], None, CFG, NOW, {}) == ([], {})
