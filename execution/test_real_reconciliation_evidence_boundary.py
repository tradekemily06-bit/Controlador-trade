from pathlib import Path

import pytest

from core.global_operational_barrier import GlobalOperationalBarrier
from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest
from execution.real_gateway import RealExecutionGateway


class UnknownAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        raise TimeoutError("dispatch timeout")


def _gateway(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    return RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lambda: GlobalOperationalBarrier()), ledger


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def _auth():
    return RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)


def _admission():
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True, broker_id="fake",
    )


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )


def test_evidence_boundary_requires_nonempty_external_reference(tmp_path: Path):
    gateway, ledger = _gateway(tmp_path)
    result = gateway.execute(
        broker="fake", request_id="unknown", request=_request(),
        authorization=_auth(), admission=_admission(), safety=_safety(),
    )
    assert result.status == "UNKNOWN"
    with pytest.raises(ValueError, match="evidence_id"):
        gateway.reconcile_unknown_with_evidence(
            "unknown", executed=True, evidence_id="", evidence_source="broker"
        )
    assert ledger.status("unknown") is ExecutionLedgerStatus.UNKNOWN


def test_evidence_boundary_resolves_without_dispatch_or_replay(tmp_path: Path):
    gateway, ledger = _gateway(tmp_path)
    gateway.execute(
        broker="fake", request_id="unknown", request=_request(),
        authorization=_auth(), admission=_admission(), safety=_safety(),
    )
    gateway.reconcile_unknown_with_evidence(
        "unknown", executed=False,
        evidence_id="reconciliation-001", evidence_source="broker-reconciliation",
    )
    assert ledger.status("unknown") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
    result = gateway.execute(
        broker="fake", request_id="unknown", request=_request(),
        authorization=_auth(), admission=_admission(), safety=_safety(),
    )
    assert result.status == "UNKNOWN"
