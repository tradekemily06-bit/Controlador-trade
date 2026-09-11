from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize_breakdowns


def make(decision_id: str, signal: str, score: float, outcome: str) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-09-11T12:00:00+00:00",
        symbol="EURUSD",
        timeframe="5m",
        signal=signal,
        score=score,
        confirmed=True,
        reason="test",
        outcome=outcome,
    )


def test_learning_breakdowns_by_signal_and_score_band():
    stats = summarize_breakdowns(
        [
            make("1", "COMPRA", 90, "WIN"),
            make("2", "COMPRA", 82, "LOSS"),
            make("3", "VENDA", 65, "WIN"),
            make("4", "AGUARDAR", 40, "LOSS"),
        ]
    )

    assert stats["signals"]["COMPRA"]["total"] == 2
    assert stats["signals"]["COMPRA"]["win_rate"] == 50.0
    assert stats["signals"]["VENDA"]["wins"] == 1
    assert stats["score_bands"]["85-100"]["total"] == 1
    assert stats["score_bands"]["70-84"]["losses"] == 1
    assert stats["score_bands"]["50-69"]["wins"] == 1
    assert stats["score_bands"]["0-49"]["losses"] == 1
