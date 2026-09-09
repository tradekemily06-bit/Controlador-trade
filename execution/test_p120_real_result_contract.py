from pathlib import Path

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class MissingExternalIdAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted but no durable reference", None)


def test_accepted_without_external_id_is_unknown_and_persisted(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", MissingExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
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
