from datetime import datetime, timezone

from core.decision_snapshot import DecisionSnapshot
from core.p49_outcome_reconciliation import ExternalOutcomeObservation
from core.operation_lineage import OperationLineage
from core.operational_runtime import build_operational_runtime
from core.market_context import MarketContext
from execution.external_outcome_port import ExternalCloseResult
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
from integration.ecosystem_service import EcosystemService


class FakeOutcomePort:
    def close_and_observe(self, request_id):
        observation = ExternalOutcomeObservation(
            cycle_id="cycle-e2e",
            outcome="WIN",
            financial_result=12.5,
            source="FAKE",
            external_reference="close-1",
            external_container_id="position-1",
            external_result_ids=("deal-1",),
            observed_at=datetime.now(timezone.utc),
        )
        return ExternalCloseResult(request_id, "position-1", "close-1", True, observation, "closed")

    def observe_closed_position(self, request_id):
        return None


def test_demo_close_flows_into_verified_memory_and_learning(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_LEARNING_DB", str(tmp_path / "learning.sqlite3"))
    runtime = build_operational_runtime(tmp_path / "runtime")
    service = EcosystemService(operational_runtime=runtime, outcome_port=FakeOutcomePort())
    record = service.analyze({
        "score": 90,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "5m",
    })
    snapshot = DecisionSnapshot(
        signal=record.signal,
        analysis_score=record.score,
        confirmed=record.confirmed,
        quality_score=90.0,
        quality_level="HIGH",
        actionable=True,
        decision="EXECUTAR",
        decision_reason=record.reason,
        market_context=MarketContext.FAVORAVEL.value,
        market_direction="ALTA",
        market_score=80.0,
        operational_state_available=True,
        trades_today=0,
        consecutive_losses=0,
        symbol=record.symbol,
        timeframe=record.timeframe,
        decision_id=record.decision_id,
        cycle_id="cycle-e2e",
        request_id="request-e2e",
    )
    runtime.operation_context.put("request-e2e", snapshot)
    runtime.lineage.put(OperationLineage(
        decision_id=record.decision_id,
        cycle_id="cycle-e2e",
        request_id="request-e2e",
        external_id="entry-1",
    ))
    runtime.execution_ledger.record("request-e2e")
    runtime.execution_lifecycle.put(ExecutionLifecycleRecord(
        "request-e2e",
        ExecutionLifecycleState.ACCEPTED,
        datetime.now(timezone.utc),
        "accepted",
    ))

    result = service.close_and_observe("request-e2e")

    assert result.observation is not None
    assert service.memory[0].outcome == "WIN"
    journal = service.post_demo_learning.post_demo.learning.journal
    assert journal.verified_note(dedupe_key="cycle:cycle-e2e").note_id == "operation-learning-cycle-e2e"


def test_unreconciled_external_observation_never_updates_operational_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_LEARNING_DB", str(tmp_path / "learning.sqlite3"))
    runtime = build_operational_runtime(tmp_path / "runtime")
    service = EcosystemService(operational_runtime=runtime, outcome_port=FakeOutcomePort())
    record = service.analyze({
        "score": 90, "confirmed": True, "filters_ok": True,
        "symbol": "EURUSD", "timeframe": "5m",
    })
    snapshot = DecisionSnapshot(
        signal=record.signal, analysis_score=record.score, confirmed=record.confirmed,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="EXECUTAR", decision_reason=record.reason,
        market_context=MarketContext.FAVORAVEL.value, market_direction="ALTA", market_score=80.0,
        operational_state_available=True, trades_today=0, consecutive_losses=0,
        symbol=record.symbol, timeframe=record.timeframe,
        decision_id=record.decision_id, cycle_id="cycle-mismatch", request_id="request-mismatch",
    )
    runtime.operation_context.put("request-mismatch", snapshot)
    runtime.lineage.put(OperationLineage(
        decision_id=record.decision_id, cycle_id="cycle-mismatch",
        request_id="request-mismatch", external_id="entry-1",
    ))
    runtime.execution_ledger.record("request-mismatch")
    runtime.execution_lifecycle.put(ExecutionLifecycleRecord(
        "request-mismatch", ExecutionLifecycleState.ACCEPTED, datetime.now(timezone.utc), "accepted",
    ))

    try:
        service.close_and_observe("request-mismatch")
    except RuntimeError as exc:
        assert "cycle_id" in str(exc)
    else:
        raise AssertionError("mismatched external evidence must fail closed")
    assert service.memory[0].outcome is None
