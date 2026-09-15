from core.models import AnalysisResult, Signal
from analysis.decision_record import DecisionRecord


def test_record_preserves_analysis_and_is_not_actionable_without_confirmation():
    result = AnalysisResult(
        signal=Signal.AGUARDAR,
        score=85,
        reason="confirmação ausente",
        confirmed=False,
        symbol="EURUSD",
        timeframe="M5",
    )

    record = DecisionRecord.from_analysis(result)

    assert record.signal == "AGUARDAR"
    assert record.score == 85
    assert record.symbol == "EURUSD"
    assert record.timeframe == "M5"
    assert record.is_actionable is False
    assert record.execution_allowed is False


def test_actionable_record_can_store_learning_outcome_without_changing_decision():
    result = AnalysisResult(
        signal=Signal.COMPRA,
        score=91,
        reason="confirmação forte",
        confirmed=True,
        symbol="EURUSD",
        timeframe="M5",
    )

    record = DecisionRecord.from_analysis(result)
    closed = record.with_outcome("WIN")

    assert record.outcome is None
    assert closed.outcome == "WIN"
    assert closed.signal == "COMPRA"
    assert closed.score == 91


def test_invalid_outcome_is_rejected():
    result = AnalysisResult(signal=Signal.VENDA, score=20, reason="ok", confirmed=True)
    record = DecisionRecord.from_analysis(result)

    try:
        record.with_outcome("MAYBE")
    except ValueError as exc:
        assert "outcome" in str(exc)
    else:
        raise AssertionError("outcome inválido deveria ser rejeitado")


def test_owner_can_be_bound_once_and_cannot_be_reassigned():
    result = AnalysisResult(signal=Signal.COMPRA, score=90, reason="ok", confirmed=True)
    record = DecisionRecord.from_analysis(result)
    owned = record.with_owner(subject_id="user-a", tenant_id="tenant-a")

    assert owned.owned_by(subject_id="user-a", tenant_id="tenant-a") is True
    assert owned.owned_by(subject_id="user-b", tenant_id="tenant-a") is False
    assert owned.owned_by(subject_id="user-a", tenant_id="tenant-b") is False
    assert owned.with_owner(subject_id="user-a", tenant_id="tenant-a") == owned

    try:
        owned.with_owner(subject_id="user-b", tenant_id="tenant-a")
    except ValueError as exc:
        assert "reassigned" in str(exc)
    else:
        raise AssertionError("ownership não deveria poder ser reassigned")


def test_owner_requires_non_empty_identity_values():
    result = AnalysisResult(signal=Signal.COMPRA, score=90, reason="ok", confirmed=True)
    record = DecisionRecord.from_analysis(result)

    for subject_id, tenant_id in (("", "tenant-a"), ("user-a", "")):
        try:
            record.with_owner(subject_id=subject_id, tenant_id=tenant_id)
        except ValueError:
            pass
        else:
            raise AssertionError("ownership vazia deveria ser rejeitada")
