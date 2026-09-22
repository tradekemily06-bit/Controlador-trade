from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class AcceptedAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted", "broker-1")


def make_gateway(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", AcceptedAdapter(), adapter_id="adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
        KillSwitch(),
    )
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm",
        audit_id="audit",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)
    return gateway, ledger, lifecycle, authorization, admission, safety, request


def test_recovery_repairs_lifecycle_after_ledger_acceptance(tmp_path):
    gateway, ledger, lifecycle, authorization, admission, safety, request = make_gateway(tmp_path)

    original_put = lifecycle.put

    def fail_acceptance(record):
        if record.state is ExecutionLifecycleState.ACCEPTED:
            raise OSError("simulated lifecycle crash window")
        return original_put(record)

    lifecycle.put = fail_acceptance
    result = gateway.execute(
        broker="fake",
        request_id="req-crash",
        request=request,
        authorization=authorization,
        admission=admission,
        safety=safety,
    )

    assert result.status is RealGatewayStatus.UNKNOWN
    assert ledger.status("req-crash") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("req-crash") == "broker-1"
    assert lifecycle.get("req-crash").state is ExecutionLifecycleState.PENDING

    lifecycle.put = original_put
    gateway.recover_lifecycle_from_durable_acceptance("req-crash")

    assert lifecycle.get("req-crash").state is ExecutionLifecycleState.ACCEPTED


def test_recovery_does_not_dispatch_again_after_ledger_acceptance(tmp_path):
    gateway, ledger, lifecycle, authorization, admission, safety, request = make_gateway(tmp_path)

    ledger.reserve("req-no-replay")
    ledger.bind_external_id("req-no-replay", "broker-1")
    ledger.mark_accepted("req-no-replay")

    lifecycle.put(
        ExecutionLifecycleRecord(
            "req-no-replay",
            ExecutionLifecycleState.PENDING,
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "crash before lifecycle acceptance",
        )
    )

    gateway.recover_lifecycle_from_durable_acceptance("req-no-replay")

    assert ledger.status("req-no-replay") is ExecutionLedgerStatus.ACCEPTED
    assert lifecycle.get("req-no-replay").state is ExecutionLifecycleState.ACCEPTED
