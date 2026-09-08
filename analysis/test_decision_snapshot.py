from analysis.decision_snapshot import DecisionSnapshotBuilder
from core.models import AnalysisResult, Signal
from core.signal_quality import SignalLevel


def test_snapshot_preserves_analysis_and_adds_quality():
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=100,
        reason="Score forte e confirmação aprovados para compra.",
        confirmed=True,
        symbol="TEST",
        timeframe="5m",
    )

    snapshot = DecisionSnapshotBuilder().build(analysis)

    assert snapshot.analysis == analysis
    assert snapshot.signal == Signal.COMPRA
    assert snapshot.score == 100
    assert snapshot.confirmed is True
    assert snapshot.reason == analysis.reason
    assert snapshot.quality.level == SignalLevel.FORTE
    assert snapshot.quality.actionable is True


def test_snapshot_is_fail_closed_for_waiting_signal():
    analysis = AnalysisResult(
        signal=Signal.AGUARDAR,
        score=50,
        reason="Score insuficiente para entrada.",
        confirmed=True,
    )

    snapshot = DecisionSnapshotBuilder().build(analysis)

    assert snapshot.signal == Signal.AGUARDAR
    assert snapshot.quality.level == SignalLevel.NENHUMA
    assert snapshot.quality.actionable is False
