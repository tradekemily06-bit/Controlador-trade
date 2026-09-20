from core.kill_switch import KillSwitch
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.models import Signal
from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator
from core.runtime_checkpoint import RuntimeCheckpointStore
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


def _gateway(tmp_path: Path, registry: BrokerRegistry, ledger: ExecutionLedger, *, kill_switch: KillSwitch | None = None, lifecycle: ExecutionLifecycleStore | None = None) -> RealExecutionGateway:
    lifecycle = lifecycle or ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "runtime-checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle=lifecycle,
        recovery=recovery,
        kill_switch=kill_switch or KillSwitch(),
    )


def test_real_gateway_requires_durable_lifecycle_and_recovery(tmp_path: Path):
    registry = BrokerRegistry()
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    with pytest.raises(ValueError, match="lifecycle"):
        RealExecutionGateway(
            BrokerAdapterGateway(registry),
            ledger,
            recovery=RecoveryCoordinator(
                checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
                lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
                execution_ledger=ledger,
                memory=OperationMemory(),
            ),
            kill_switch=KillSwitch(),
        )

    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    with pytest.raises(ValueError, match="recovery"):
        RealExecutionGateway(
            BrokerAdapterGateway(registry),
            ledger,
            lifecycle=lifecycle,
            kill_switch=KillSwitch(),
        )


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


class UnavailableAdapter:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return False

    def execute(self, request):
        self.calls += 1
        raise AssertionError("adapter indisponível não pode ser chamado")



def test_final_boundary_blocks_reconciled_not_executed(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = UnavailableAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("terminal-not-executed")
    ledger._reconcile_locked("terminal-not-executed", executed=False)
    lifecycle.put(ExecutionLifecycleRecord("terminal-not-executed", ExecutionLifecycleState.REJECTED, datetime.now(timezone.utc), "reconciled"))
    gateway = _gateway(tmp_path, registry, ledger, lifecycle=lifecycle)
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "fake", True, True)
    admission = RealAdmissionBoundary().admit(admission_id="adm", audit_id="audit", audit_verified=True, authorization_active=True, safety_ready=True, broker_available=True, broker_id="fake")
    safety = RealSafetyGate().evaluate(authorization_active=True, kill_switch_clear=True, market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True)
    result = gateway.execute(broker="fake", request_id="terminal-not-executed", request=_request(), authorization=authorization, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_pre_dispatch_adapter_block_is_terminal_not_unknown(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnavailableAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = _gateway(tmp_path, registry, ledger)
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    result = gateway.execute(
        broker="fake", request_id="pre-dispatch-block", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert ledger.status("pre-dispatch-block") is ExecutionLedgerStatus.REJECTED
    assert gateway._lifecycle.get("pre-dispatch-block").state.name == "REJECTED"


class MissingExternalIdAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted but no durable reference", None)


def test_accepted_without_external_id_is_unknown_and_persisted(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", MissingExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = _gateway(tmp_path, registry, ledger)
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    result = gateway.execute(
        broker="fake", request_id="missing-external-id", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("missing-external-id") is ExecutionLedgerStatus.UNKNOWN


class FailingAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        raise RuntimeError("timeout after send")


def test_adapter_transport_failure_is_unknown_not_rejected(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", FailingAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = _gateway(tmp_path, registry, ledger)
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    result = gateway.execute(
        broker="fake", request_id="transport-uncertain", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("transport-uncertain") is ExecutionLedgerStatus.UNKNOWN


class RejectedWithExternalIdAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(False, "rejected with broker reference", "EXT-REJECTED-1")


def test_rejected_response_with_external_id_is_unknown_and_reconcilable(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", RejectedWithExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = _gateway(tmp_path, registry, ledger)
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    result = gateway.execute(
        broker="fake", request_id="rejected-with-id", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("rejected-with-id") is ExecutionLedgerStatus.UNKNOWN
    assert ledger.external_id("rejected-with-id") == "EXT-REJECTED-1"


class ActivatingAdapter:
    def __init__(self, kill_switch):
        self.kill_switch = kill_switch
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        self.kill_switch.activate("test activation at broker boundary")
        return ExecutionResult(True, "accepted", f"EXT-{self.calls}")


def test_live_kill_switch_overrides_stale_ready_report_at_real_boundary(tmp_path: Path):
    kill_switch = KillSwitch()
    adapter = ActivatingAdapter(kill_switch)
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = _gateway(tmp_path, registry, ledger, kill_switch=kill_switch)
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    first = gateway.execute(
        broker="fake", request_id="live-switch-1", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )
    assert first.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1
    assert kill_switch.state.enabled is True

    second = gateway.execute(
        broker="fake", request_id="live-switch-2", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )
    assert second.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1
    assert ledger.status("live-switch-2") is ExecutionLedgerStatus.REJECTED
