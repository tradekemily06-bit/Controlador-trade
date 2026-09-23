from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.external_execution_registry import ExternalExecutionRegistry
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class FakeRealAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted", "EXT-1")


def _request():
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.REAL,
    )


def _gateway(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeRealAdapter())
    adapter_gateway = BrokerAdapterGateway(registry)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    external = ExternalExecutionRegistry(tmp_path / "external.json")
    return RealExecutionGateway(adapter_gateway, ledger, external_registry=external), ledger, external


def _authorization():
    return RealExecutionAuthorization(
        authorization_id="auth-1",
        audit_id="audit-1",
        broker_id="fake",
        adapter_id="fake",
        explicitly_enabled=True,
        real_execution_allowed=True,
    )


def _admission():
    return RealAdmissionBoundary().admit(
        admission_id="admit-1",
        audit_id="audit-1",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="fake",
    )


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )


def test_real_gateway_derives_external_registry_from_ledger(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeRealAdapter())
    ledger_path = tmp_path / "ledger.json"
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(ledger_path))
    result = gateway.execute(
        broker="fake",
        request_id="req-auto-registry",
        request=_request(),
        authorization=_authorization(),
        admission=_admission(),
        safety=_safety(),
    )
    assert result.status == RealGatewayStatus.ADMITTED
    assert (tmp_path / "ledger.external.json").exists()


def test_real_gateway_binds_external_id_before_reporting_admitted(tmp_path):
    gateway, ledger, external = _gateway(tmp_path)

    result = gateway.execute(
        broker="fake",
        request_id="req-1",
        request=_request(),
        authorization=_authorization(),
        admission=_admission(),
        safety=_safety(),
    )

    assert result.status == RealGatewayStatus.ADMITTED
    assert result.execution is not None
    assert external.get("req-1") == ("fake", "EXT-1")
    assert ledger.status("req-1") is ExecutionLedgerStatus.ACCEPTED


def test_real_gateway_duplicate_external_id_becomes_unknown(tmp_path):
    gateway, ledger, external = _gateway(tmp_path)
    external.bind("other-request", "fake", "EXT-1")

    result = gateway.execute(
        broker="fake",
        request_id="req-1",
        request=_request(),
        authorization=_authorization(),
        admission=_admission(),
        safety=_safety(),
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("req-1") is ExecutionLedgerStatus.UNKNOWN
