from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.models import Signal
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.operation_memory import OperationMemory
from core.runtime_checkpoint import RuntimeCheckpointStore
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
from execution.real_composition import build_real_execution_gateway
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class FakeAdapter:
    def __init__(self, result: ExecutionResult | None = None):
        self.calls = 0
        self.result = result or ExecutionResult(True, "accepted", "ext-1")

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return self.result


class ExplodingLifecycle(ExecutionLifecycleStore):
    def put(self, record):
        if record.state is ExecutionLifecycleState.ACCEPTED:
            raise OSError("lifecycle write failed")
        return super().put(record)


def request():
    return ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL)


def auth():
    return RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)


def admission():
    return RealAdmissionBoundary().admit(
        admission_id="adm",
        audit_id="audit",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="fake",
    )


def safety():
    return RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )


def gateway(tmp_path: Path, adapter: FakeAdapter, lifecycle=True):
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")
    store = (
        ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
        if lifecycle
        else None
    )
    return RealExecutionGateway(BrokerAdapterGateway(registry), ledger, store), ledger, store


def execute(gateway, request_id="r1"):
    return gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request(),
        authorization=auth(),
        admission=admission(),
        safety=safety(),
    )


def test_accepted_external_id_is_durable(tmp_path):
    adapter = FakeAdapter(ExecutionResult(True, "accepted", "broker-123"))
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    result = execute(gw)
    assert result.status == RealGatewayStatus.ADMITTED
    assert ledger.status("r1") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("r1") == "broker-123"
    assert lifecycle.get("r1").state is ExecutionLifecycleState.ACCEPTED
    assert ExecutionLedger(tmp_path / "execution-ledger.json").external_id("r1") == "broker-123"


def test_accepted_but_lifecycle_failure_does_not_erase_ledger_authority(tmp_path):
    adapter = FakeAdapter(ExecutionResult(True, "accepted", "broker-456"))
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")
    lifecycle = ExplodingLifecycle(tmp_path / "execution-lifecycle.json")
    gw = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle)
    result = execute(gw)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("r1") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("r1") == "broker-456"


@pytest.mark.parametrize("external_id", ["broker-rejected", None])
def test_rejection_with_or_without_external_id_is_terminal(tmp_path, external_id):
    adapter = FakeAdapter(ExecutionResult(False, "rejected", external_id))
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    result = execute(gw)
    assert result.status == RealGatewayStatus.REJECTED
    assert ledger.status("r1") is ExecutionLedgerStatus.REJECTED
    assert ledger.external_id("r1") == external_id
    assert lifecycle.get("r1").state is ExecutionLifecycleState.REJECTED


def test_accepted_without_external_id_is_unknown_and_never_promoted_locally(tmp_path):
    adapter = FakeAdapter(ExecutionResult(True, "accepted", None))
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    result = execute(gw)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("r1") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("r1").state is ExecutionLifecycleState.UNKNOWN
    with pytest.raises(ValueError):
        lifecycle.put(
            ExecutionLifecycleRecord(
                "r1",
                ExecutionLifecycleState.ACCEPTED,
                datetime.now(timezone.utc),
            )
        )


def test_restart_with_reserved_never_reexecutes(tmp_path):
    adapter = FakeAdapter()
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("crash")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "crash", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )
    result = execute(gw, "crash")
    assert result.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 0


def test_two_gateway_instances_same_request_are_idempotent(tmp_path):
    adapter = FakeAdapter()
    first, ledger, lifecycle = gateway(tmp_path, adapter)
    second, _, _ = gateway(tmp_path, adapter)
    assert execute(first, "same") .status == RealGatewayStatus.ADMITTED
    assert execute(second, "same").status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1


def test_recovery_requires_reconciliation_for_every_mismatch(tmp_path):
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    cases = [
        (ExecutionLedgerStatus.RESERVED, ExecutionLifecycleState.PENDING),
        (ExecutionLedgerStatus.UNKNOWN, ExecutionLifecycleState.UNKNOWN),
        (ExecutionLedgerStatus.ACCEPTED, ExecutionLifecycleState.PENDING),
        (ExecutionLedgerStatus.REJECTED, ExecutionLifecycleState.ACCEPTED),
    ]
    for index, (ledger_status, lifecycle_state) in enumerate(cases):
        request_id = f"case-{index}"
        ledger.reserve(request_id)
        if ledger_status is ExecutionLedgerStatus.ACCEPTED:
            ledger.mark_accepted(request_id, "ext")
        elif ledger_status is ExecutionLedgerStatus.REJECTED:
            ledger.mark_rejected(request_id)
        elif ledger_status is ExecutionLedgerStatus.UNKNOWN:
            ledger.mark_unknown(request_id)
        lifecycle.put(
            ExecutionLifecycleRecord(
                request_id, lifecycle_state, datetime.now(timezone.utc)
            )
        )

    recovery = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    assessment = recovery.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert set(assessment.unknown_request_ids) >= {"case-0", "case-1"}
    

def test_recovery_detects_ledger_without_lifecycle(tmp_path):
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")
    ledger.reserve("orphan")
    lifecycle = ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    assert recovery.assess().state is RecoveryState.REQUIRES_RECONCILIATION


def test_sanctioned_composition_is_the_production_constructor(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    gw = build_real_execution_gateway(root=tmp_path, registry=registry)
    assert isinstance(gw, RealExecutionGateway)


def test_no_direct_adapter_execute_call_outside_adapter_gateway():
    root = Path(__file__).resolve().parent
    violations = []
    for path in root.glob("*.py"):
        if path.name in {"adapter_gateway.py"} or path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "execute" and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "adapter":
                        violations.append(f"{path.name}:{node.lineno}")
    assert violations == []


def test_real_gateway_is_constructed_only_by_sanctioned_composition():
    root = Path(__file__).resolve().parent
    violations = []
    for path in root.glob("*.py"):
        if path.name in {"real_gateway.py", "real_composition.py"} or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        if "RealExecutionGateway(" in text:
            violations.append(path.name)
    assert violations == []
