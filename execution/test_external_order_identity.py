from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class ExternalIdAdapter:
    def __init__(self, external_id: str):
        self.external_id = external_id
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "accepted", self.external_id)


def _request(request_id: str) -> ExecutionRequest:
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id)


def _auth() -> RealExecutionAuthorization:
    return RealExecutionAuthorization("auth", "audit", "fake", "adapter-1", True, True)


def _admit_and_safety():
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
    return admission, safety


def test_external_identity_binds_request_and_survives_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-1")
    ledger.mark_accepted("req-1", broker="fake", adapter="adapter-1", external_id="order-42")

    restored = ExecutionLedger(path)
    assert restored.status("req-1") is ExecutionLedgerStatus.ACCEPTED
    assert restored.external_binding(broker="FAKE", adapter="ADAPTER-1", external_id="order-42") == "req-1"


def test_external_identity_collision_is_rejected_atomically(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1")
    ledger.reserve("req-2")
    ledger.mark_accepted("req-1", broker="fake", adapter="adapter-1", external_id="order-42")

    with pytest.raises(ValueError, match="external order identity"):
        ledger.mark_accepted("req-2", broker="fake", adapter="adapter-1", external_id="order-42")

    assert ledger.status("req-2") is ExecutionLedgerStatus.RESERVED
    assert ledger.external_binding(broker="fake", adapter="adapter-1", external_id="order-42") == "req-1"


def test_real_gateway_collision_becomes_unknown_without_resubmission(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("already-bound")
    ledger.mark_accepted("already-bound", broker="fake", adapter="adapter-1", external_id="order-42")

    registry = BrokerRegistry()
    adapter = ExternalIdAdapter("order-42")
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path), KillSwitch())
    auth = _auth()
    admission, safety = _admit_and_safety()

    result = gateway.execute(
        broker="fake", request_id="new-request", request=_request("new-request"),
        authorization=auth, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ExecutionLedger(path).status("new-request") is ExecutionLedgerStatus.UNKNOWN
    assert adapter.calls == 1
