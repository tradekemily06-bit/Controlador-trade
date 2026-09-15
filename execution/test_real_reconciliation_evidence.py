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


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def _auth():
    return RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)


def _admission():
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )


def _gateway(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, lambda: GlobalOperationalBarrier()
    )
    return gateway, ledger


def test_reconciliation_requires_explicit_external_evidence(tmp_path: Path):
    gateway, ledger = _gateway(tmp_path)
    first = gateway.execute(
        broker="fake", request_id="unknown", request=_request(),
        authorization=_auth(), admission=_admission(), safety=_safety(),
    )
    assert first.status.value == "UNKNOWN"

    with pytest.raises(ValueError, match="evidência externa"):
        gateway.reconcile_unknown("unknown", executed=True)

    assert ledger.status("unknown") is ExecutionLedgerStatus.UNKNOWN


def test_reconciliation_accepts_only_explicit_terminal_evidence(tmp_path: Path):
    gateway, ledger = _gateway(tmp_path)
    gateway.execute(
        broker="fake", request_id="unknown", request=_request(),
        authorization=_auth(), admission=_admission(), safety=_safety(),
    )

    gateway.reconcile_unknown(
        "unknown", executed=True,
        evidence_id="broker-order-123", evidence_source="broker-reconciliation",
    )

    assert ledger.status("unknown") is ExecutionLedgerStatus.RECONCILED_EXECUTED


def test_reconciled_request_cannot_be_submitted_again(tmp_path: Path):
    gateway, ledger = _gateway(tmp_path)
    gateway.reconcile_unknown.__self__
    ledger.reserve("already-unknown")
    ledger.mark_unknown("already-unknown")
    gateway.reconcile_unknown(
        "already-unknown", executed=False,
        evidence_id="broker-reconciliation-456", evidence_source="broker-reconciliation",
    )

    result = gateway.execute(
        broker="fake", request_id="already-unknown", request=_request(),
        authorization=_auth(), admission=_admission(), safety=_safety(),
    )
    assert result.status.value == "UNKNOWN"
    assert ledger.status("already-unknown") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
