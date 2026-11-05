from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from core.kill_switch import KillSwitch
from core.real_runtime_controller import RealRuntimeController
from execution.ports import ExecutionResult


class FakeRecovery:
    def assess(self):
        from core.recovery_coordinator import RecoveryAssessment, RecoveryState
        return RecoveryAssessment(RecoveryState.FRESH, ())


class FakeRuntime:
    def __init__(self, tmp_path):
        from execution.execution_ledger import ExecutionLedger
        from execution.execution_lifecycle import ExecutionLifecycleStore
        self.execution_lifecycle = ExecutionLifecycleStore(Path(tmp_path) / "lifecycle.json")
        self.kill_switch = KillSwitch()
        self.market_data = type("MarketData", (), {"report": type("Report", (), {"safe_for_analysis": True})()})()
        self.recovery = FakeRecovery()
        self.execution_ledger = ExecutionLedger(Path(tmp_path) / "ledger.json")


def test_real_controller_fails_closed_without_explicit_deployment_flags(monkeypatch, tmp_path):
    for name in (
        "CONTROLADOR_REAL_AUTHORIZATION_ID",
        "CONTROLADOR_REAL_AUDIT_ID",
        "CONTROLADOR_REAL_ADMISSION_ID",
        "CONTROLADOR_REAL_EXPLICITLY_ENABLED",
        "CONTROLADOR_REAL_EXECUTION_ALLOWED",
        "CONTROLADOR_REAL_AUDIT_VERIFIED",
        "CONTROLADOR_REAL_RISK_APPROVED",
    ):
        monkeypatch.delenv(name, raising=False)

    controller = RealRuntimeController(runtime=FakeRuntime(tmp_path), root=tmp_path)
    status = controller.status()
    assert status["authorization_active"] is False
    assert status["safety_ready"] is False
    assert status["admitted"] is False


def test_real_controller_prepare_requires_all_explicit_prerequisites(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROLADOR_REAL_AUTHORIZATION_ID", "auth")
    monkeypatch.setenv("CONTROLADOR_REAL_AUDIT_ID", "audit")
    monkeypatch.setenv("CONTROLADOR_REAL_ADMISSION_ID", "admission")
    monkeypatch.setenv("CONTROLADOR_REAL_EXPLICITLY_ENABLED", "true")
    monkeypatch.setenv("CONTROLADOR_REAL_EXECUTION_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_REAL_AUDIT_VERIFIED", "true")
    monkeypatch.setenv("CONTROLADOR_REAL_RISK_APPROVED", "true")

    controller = RealRuntimeController(runtime=FakeRuntime(tmp_path), root=tmp_path, symbol="EURUSD")
    status = controller.status()
    assert status["authorization_active"] is True
    assert status["safety_ready"] is False or status["admitted"] is False


def test_real_close_requires_accepted_ledger_state_before_adapter_access():
    source = (Path(__file__).parent / "real_runtime_controller.py").read_text(encoding="utf-8")
    method = source.split("    def close_and_reconcile(", 1)[1].split(
        "    def reconcile(", 1
    )[0]

    state_guard = "record.status is not ExecutionLedgerStatus.ACCEPTED"
    assert state_guard in method
    assert method.index(state_guard) < method.index("self.registry.get(self.broker_id)")


def test_real_close_rejects_blank_external_id_before_ledger_access():
    source = (Path(__file__).parent / "real_runtime_controller.py").read_text(encoding="utf-8")
    method = source.split("    def close_and_reconcile(", 1)[1].split(
        "    def reconcile(", 1
    )[0]

    validation = "not isinstance(external_id, str) or not external_id.strip()"
    assert validation in method
    assert method.index(validation) < method.index(
        "self.runtime.execution_ledger.record_for(request_id)"
    )


def test_real_reconcile_rejects_non_boolean_outcome_before_gateway_call():
    source = (Path(__file__).parent / "real_runtime_controller.py").read_text(encoding="utf-8")
    method = source.split("    def reconcile(", 1)[1]

    validation = "if not isinstance(executed, bool):"
    assert validation in method
    assert method.index(validation) < method.index("self.gateway.reconcile_unknown")
    assert "executed=executed" in method
    assert "executed=bool(executed)" not in method


class FakeCloseAdapter:
    def __init__(self, observation=None):
        self.calls = 0
        self.observation_calls = 0
        self.observation = observation
        self.started = Event()
        self.release = Event()

    def reconcile_position_close(self, external_id):
        self.observation_calls += 1
        return self.observation

    def close_position(self, external_id):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
        return ExecutionResult(True, "posição encerrada pelo adaptador de teste.", "close-1")


class FakeRegistry:
    def __init__(self, adapter):
        self.adapter = adapter

    def get(self, broker_id):
        return self.adapter


def test_real_close_serializes_concurrent_requests_and_prevents_duplicate_adapter_call(tmp_path):
    from datetime import datetime, timezone

    from execution.execution_ledger import ExecutionLedgerStatus
    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
    from execution.position_close_store import PositionCloseState

    runtime = FakeRuntime(tmp_path)
    runtime.execution_ledger.reserve("req-close", cycle_id="cycle-close")
    runtime.execution_ledger.bind_external_id("req-close", "ticket-123")
    runtime.execution_ledger.mark_accepted("req-close")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord(
            "req-close",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
            "ordem aceita",
        )
    )

    adapter = FakeCloseAdapter()
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.registry = FakeRegistry(adapter)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            controller.close_and_reconcile,
            request_id="req-close",
            external_id="ticket-123",
        )
        assert adapter.started.wait(timeout=1)
        second = pool.submit(
            controller.close_and_reconcile,
            request_id="req-close",
            external_id="ticket-123",
        )
        adapter.release.set()
        result = first.result(timeout=2)
        with pytest.raises(ValueError, match="fechamento já solicitado ou concluído"):
            second.result(timeout=2)

    assert result.accepted is True
    assert adapter.calls == 1
    assert runtime.execution_ledger.status("req-close") is ExecutionLedgerStatus.ACCEPTED
    assert runtime.execution_lifecycle.get("req-close").state is ExecutionLifecycleState.ACCEPTED
    assert controller.position_closes.get("req-close").state is PositionCloseState.CLOSED


def test_real_close_persists_intent_and_blocks_retry_after_controller_restart(tmp_path):
    from datetime import datetime, timezone

    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
    from execution.position_close_store import PositionCloseState, PositionCloseStore

    runtime = FakeRuntime(tmp_path)
    runtime.execution_ledger.reserve("req-restart", cycle_id="cycle-restart")
    runtime.execution_ledger.bind_external_id("req-restart", "ticket-456")
    runtime.execution_ledger.mark_accepted("req-restart")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord(
            "req-restart",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
            "ordem aceita",
        )
    )

    adapter = FakeCloseAdapter()
    adapter.release.set()
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.registry = FakeRegistry(adapter)
    result = controller.close_and_reconcile(
        request_id="req-restart",
        external_id="ticket-456",
    )
    assert result.accepted is True

    # Re-open the durable store as a fresh controller process would.
    recovered = PositionCloseStore(Path(tmp_path) / "real-position-closes.json")
    assert recovered.get("req-restart").state is PositionCloseState.ACCEPTED

    retry_adapter = FakeCloseAdapter()
    retry_adapter.release.set()
    restarted_controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    restarted_controller.registry = FakeRegistry(retry_adapter)
    with pytest.raises(ValueError, match="fechamento já solicitado ou concluído"):
        restarted_controller.close_and_reconcile(
            request_id="req-restart",
            external_id="ticket-456",
        )
    assert retry_adapter.calls == 0


def test_real_close_records_unknown_and_blocks_retry_after_adapter_exception(tmp_path):
    from datetime import datetime, timezone

    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
    from execution.position_close_store import PositionCloseState

    class RaisingAdapter:
        def close_position(self, external_id):
            raise TimeoutError("broker response timed out")

    runtime = FakeRuntime(tmp_path)
    runtime.execution_ledger.reserve("req-timeout", cycle_id="cycle-timeout")
    runtime.execution_ledger.bind_external_id("req-timeout", "ticket-789")
    runtime.execution_ledger.mark_accepted("req-timeout")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord(
            "req-timeout",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
            "ordem aceita",
        )
    )
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.registry = FakeRegistry(RaisingAdapter())

    with pytest.raises(TimeoutError):
        controller.close_and_reconcile(
            request_id="req-timeout",
            external_id="ticket-789",
        )
    assert controller.position_closes.get("req-timeout").state is PositionCloseState.UNKNOWN

    retry_adapter = FakeCloseAdapter()
    retry_adapter.release.set()
    retry_controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    retry_controller.registry = FakeRegistry(retry_adapter)
    with pytest.raises(ValueError, match="fechamento já solicitado ou concluído"):
        retry_controller.close_and_reconcile(
            request_id="req-timeout",
            external_id="ticket-789",
        )
    assert retry_adapter.calls == 0


def test_real_controller_reports_unresolved_close_and_fails_closed_for_new_entries(tmp_path):
    from datetime import datetime, timezone

    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
    from execution.position_close_store import PositionCloseState

    runtime = FakeRuntime(tmp_path)
    runtime.execution_ledger.reserve("req-unknown-close", cycle_id="cycle-unknown-close")
    runtime.execution_ledger.bind_external_id("req-unknown-close", "ticket-999")
    runtime.execution_ledger.mark_accepted("req-unknown-close")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord(
            "req-unknown-close",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
            "ordem aceita",
        )
    )
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.position_closes.begin("req-unknown-close", "ticket-999")
    controller.position_closes.finish(
        "req-unknown-close",
        PositionCloseState.UNKNOWN,
        message="resposta do broker incerta",
    )

    status = controller.status()
    assert status["position_close_recovery_required"] is True
    assert status["unresolved_position_closes"] == 1
    assert controller._position_close_recovery_required() is True


def test_real_controller_treats_corrupt_close_history_as_recovery_required(tmp_path):
    runtime = FakeRuntime(tmp_path)
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.position_closes.path.write_text("{invalid", encoding="utf-8")
    assert controller._position_close_recovery_required() is True
    status = controller.status()
    assert status["position_close_recovery_required"] is True
    assert status["unresolved_position_closes"] is None


def test_real_close_reconciliation_uses_read_only_broker_evidence(tmp_path):
    from datetime import datetime, timezone

    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
    from execution.position_close_store import PositionCloseState
    from execution.ports import PositionCloseObservation, PositionCloseObservationStatus

    runtime = FakeRuntime(tmp_path)
    runtime.execution_ledger.reserve("req-reconcile", cycle_id="cycle-reconcile")
    runtime.execution_ledger.bind_external_id("req-reconcile", "ticket-321")
    runtime.execution_ledger.mark_accepted("req-reconcile")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord(
            "req-reconcile",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
            "ordem aceita",
        )
    )
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.position_closes.begin("req-reconcile", "ticket-321")
    controller.position_closes.finish(
        "req-reconcile",
        PositionCloseState.UNKNOWN,
        message="resposta perdida",
    )
    adapter = FakeCloseAdapter(
        PositionCloseObservation(
            PositionCloseObservationStatus.CLOSED,
            "histórico de saída confirmado",
        )
    )
    controller.registry = FakeRegistry(adapter)

    result = controller.reconcile_position_close(
        request_id="req-reconcile",
        external_id="ticket-321",
    )

    assert result["state"] == "CLOSED"
    assert result["read_only"] is True
    assert result["order_sent"] is False
    assert adapter.observation_calls == 1
    assert adapter.calls == 0
    assert controller.position_closes.get("req-reconcile").state is PositionCloseState.ACCEPTED
    assert controller._position_close_recovery_required() is False


def test_open_position_reconciliation_allows_only_a_new_explicit_close_request(tmp_path):
    from datetime import datetime, timezone

    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
    from execution.position_close_store import PositionCloseState
    from execution.ports import PositionCloseObservation, PositionCloseObservationStatus

    runtime = FakeRuntime(tmp_path)
    runtime.execution_ledger.reserve("req-open", cycle_id="cycle-open")
    runtime.execution_ledger.bind_external_id("req-open", "ticket-654")
    runtime.execution_ledger.mark_accepted("req-open")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord(
            "req-open",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
            "ordem aceita",
        )
    )
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.position_closes.begin("req-open", "ticket-654")
    controller.position_closes.finish(
        "req-open",
        PositionCloseState.UNKNOWN,
        message="resultado incerto",
    )
    adapter = FakeCloseAdapter(
        PositionCloseObservation(
            PositionCloseObservationStatus.OPEN,
            "posição continua aberta",
        )
    )
    controller.registry = FakeRegistry(adapter)

    result = controller.reconcile_position_close(
        request_id="req-open",
        external_id="ticket-654",
    )
    assert result["state"] == "OPEN"
    assert controller._position_close_recovery_required() is False

    # A later call to close_and_reconcile is an explicit new request by caller;
    # the reconciliation operation itself never dispatched a close.
    close_adapter = FakeCloseAdapter()
    close_adapter.release.set()
    controller.registry = FakeRegistry(close_adapter)
    close_result = controller.close_and_reconcile(
        request_id="req-open",
        external_id="ticket-654",
    )
    assert close_result.accepted is True
    assert close_adapter.calls == 1
    assert adapter.calls == 0


def test_real_controller_status_exposes_only_unresolved_close_records(tmp_path):
    from execution.position_close_store import PositionCloseState

    runtime = FakeRuntime(tmp_path)
    controller = RealRuntimeController(runtime=runtime, root=tmp_path)
    controller.position_closes.begin("req-visible", "ticket-visible")
    controller.position_closes.finish(
        "req-visible",
        PositionCloseState.UNKNOWN,
        message="ambiguous",
    )
    controller.position_closes.begin("req-open-resolved", "ticket-open")
    controller.position_closes.reconcile(
        "req-open-resolved",
        PositionCloseState.OPEN,
        message="still open",
    )

    status = controller.status()
    assert status["unresolved_position_closes"] == 1
    assert status["position_close_recovery_items"] == [
        {
            "request_id": "req-visible",
            "external_id": "ticket-visible",
            "state": "UNKNOWN",
            "attempt": 1,
            "updated_at": controller.position_closes.get("req-visible").updated_at.isoformat(),
            "message": "ambiguous",
        }
    ]
