from pathlib import Path

from core.global_operational_barrier import GlobalOperationalBarrier
from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode, ExecutionRequest
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


def _gateway(path: Path) -> RealExecutionGateway:
    return RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ExecutionLedger(path),
        operational_barrier_provider=GlobalOperationalBarrier,
    )


def _request(request_id="req"):
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id)


def _authorization(audit="audit", broker="fake"):
    return RealExecutionAuthorization("auth", audit, broker, "adapter", True, True)


def _admission(audit="audit", broker="fake"):
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id=audit, audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id=broker,
    )


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True,
        risk_approved=True, broker_available=True,
    )


def test_real_gateway_rejects_stale_admission_audit(tmp_path: Path):
    result = _gateway(tmp_path / "ledger.json").execute(
        broker="fake", request_id="audit-mismatch", request=_request("audit-mismatch"),
        authorization=_authorization(audit="audit-new"), admission=_admission(audit="audit-old"),
        safety=_safety(),
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert "auditoria" in result.message
    assert ExecutionLedger(tmp_path / "ledger.json").status("audit-mismatch") is None


def test_real_gateway_rejects_admission_for_different_broker(tmp_path: Path):
    result = _gateway(tmp_path / "ledger.json").execute(
        broker="fake", request_id="broker-mismatch", request=_request("broker-mismatch"),
        authorization=_authorization(broker="fake"), admission=_admission(broker="other"),
        safety=_safety(),
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert "broker" in result.message
    assert ExecutionLedger(tmp_path / "ledger.json").status("broker-mismatch") is None
