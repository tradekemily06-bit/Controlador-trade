from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from multiprocessing import Process, Queue

import pytest

from core.models import Signal
from core.operation_memory import OperationMemory
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.adapter_gateway import BrokerAdapterGateway, _REAL_DISPATCH_CAPABILITY
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
    supports_real_execution = True
    adapter_id = "adapter"

    def __init__(self, result: ExecutionResult | None = None, observation=None):
        self.calls = 0
        self.result = result or ExecutionResult(True, "accepted", "ext-1")
        self.observation = observation
        self.query_calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return self.result

    def query_order(self, external_id):
        self.query_calls += 1
        if self.observation is None or external_id != self.observation.external_id:
            raise ValueError("unexpected external_id")
        return self.observation


class DemoOnlyAdapter:
    supports_real_execution = False

    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "demo accepted", "demo-ext")


class ExplodingLifecycle(ExecutionLifecycleStore):
    def put(self, record):
        if record.state is ExecutionLifecycleState.ACCEPTED:
            raise OSError("lifecycle write failed")
        return super().put(record)


class ExplodingReconcileLifecycle(ExecutionLifecycleStore):
    def reconcile(self, *args, **kwargs):
        raise OSError("lifecycle reconcile failed")


class QueryPort:
    def __init__(self, observation):
        self.observation = observation
        self.calls = 0

    def query_order(self, external_id):
        self.calls += 1
        if external_id != self.observation.external_id:
            raise ValueError("unexpected external_id")
        return self.observation


def request(request_id="r1"):
    return ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL, request_id=request_id)


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


def gateway(tmp_path: Path, adapter, lifecycle=True):
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")
    store = (
        ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
        if lifecycle
        else None
    )
    return RealExecutionGateway(BrokerAdapterGateway(registry), ledger, store), ledger, store


def execute(gw, request_id="r1"):
    return gw.execute(
        broker="fake",
        request_id=request_id,
        request=request(request_id),
        authorization=auth(),
        admission=admission(),
        safety=safety(),
    )


def test_real_request_id_must_match_request_payload(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())
    result = gw.execute(
        broker="fake",
        request_id="outer-id",
        request=request("inner-id"),
        authorization=auth(),
        admission=admission(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED


def test_real_admission_must_match_authorization_context(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())
    mismatched = RealAdmissionBoundary().admit(
        admission_id="adm",
        audit_id="different-audit",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="other-broker",
    )
    result = gw.execute(
        broker="fake",
        request_id="r1",
        request=request("r1"),
        authorization=auth(),
        admission=mismatched,
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED


def test_accepted_external_id_is_durable(tmp_path):
    gw, ledger, lifecycle = gateway(
        tmp_path, FakeAdapter(ExecutionResult(True, "accepted", "broker-123"))
    )
    result = execute(gw)
    assert result.status == RealGatewayStatus.ADMITTED
    assert ledger.status("r1") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("r1") == "broker-123"
    assert lifecycle.get("r1").state is ExecutionLifecycleState.ACCEPTED
    assert ExecutionLedger(tmp_path / "execution-ledger.json").external_id("r1") == "broker-123"


def test_accepted_but_lifecycle_failure_keeps_ledger_authority(tmp_path):
    registry = BrokerRegistry()
    adapter = FakeAdapter(ExecutionResult(True, "accepted", "broker-456"))
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
    gw, ledger, lifecycle = gateway(
        tmp_path, FakeAdapter(ExecutionResult(False, "rejected", external_id))
    )
    result = execute(gw)
    assert result.status == RealGatewayStatus.REJECTED
    assert ledger.status("r1") is ExecutionLedgerStatus.REJECTED
    assert ledger.external_id("r1") == external_id
    assert lifecycle.get("r1").state is ExecutionLifecycleState.REJECTED


def test_accepted_without_external_id_becomes_unknown(tmp_path):
    gw, ledger, lifecycle = gateway(
        tmp_path, FakeAdapter(ExecutionResult(True, "accepted", None))
    )
    result = execute(gw)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("r1") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("r1").state is ExecutionLifecycleState.UNKNOWN


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
    first, _, _ = gateway(tmp_path, adapter)
    second, _, _ = gateway(tmp_path, adapter)
    assert execute(first, "same").status == RealGatewayStatus.ADMITTED
    assert execute(second, "same").status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1


def test_ledger_rejects_normal_promotion_from_unknown(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("unknown")
    ledger.mark_unknown("unknown")
    with pytest.raises(ValueError, match="UNKNOWN"):
        ledger.mark_accepted("unknown", "broker-1")
    with pytest.raises(ValueError, match="UNKNOWN"):
        ledger.mark_rejected("unknown")


def test_ledger_requires_external_id_for_accepted(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("accepted")
    with pytest.raises(ValueError, match="external_id"):
        ledger.mark_accepted("accepted")


def test_ledger_requires_external_id_for_executed_reconciliation(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("reconcile")
    with pytest.raises(ValueError, match="external_id"):
        ledger.reconcile("reconcile", executed=True)


def _reserve_in_process(path, request_id, queue):
    try:
        ExecutionLedger(path).reserve(request_id)
    except Exception as exc:
        queue.put(type(exc).__name__)
    else:
        queue.put("OK")


def test_ledger_reservation_allows_distinct_interprocess_requests(tmp_path):
    path = tmp_path / "ledger-distinct.json"
    queue = Queue()
    processes = [
        Process(target=_reserve_in_process, args=(path, f"request-{i}", queue))
        for i in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
    results = sorted(queue.get(timeout=5) for _ in processes)
    assert results == ["OK", "OK"]
    ledger = ExecutionLedger(path)
    assert ledger.status("request-0") is ExecutionLedgerStatus.RESERVED
    assert ledger.status("request-1") is ExecutionLedgerStatus.RESERVED


def test_ledger_reservation_is_interprocess_single_winner(tmp_path):
    path = tmp_path / "ledger.json"
    queue = Queue()
    processes = [
        Process(target=_reserve_in_process, args=(path, "same-request", queue))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
    results = sorted(queue.get(timeout=5) for _ in processes)
    assert results == ["OK", "ValueError"]
    assert ExecutionLedger(path).status("same-request") is ExecutionLedgerStatus.RESERVED


def test_ledger_requires_external_id_for_not_executed_reconciliation(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("reconcile-not-executed")
    with pytest.raises(ValueError, match="external_id"):
        ledger.reconcile("reconcile-not-executed", executed=False)


def test_legacy_status_only_terminal_records_are_quarantined(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('["legacy-1"]', encoding="utf-8")
    ledger = ExecutionLedger(path)
    assert ledger.status("legacy-1") is ExecutionLedgerStatus.UNKNOWN
    assert ledger.external_id("legacy-1") is None


def test_structured_terminal_without_external_id_is_quarantined(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(
        '{"a": {"status": "ACCEPTED"}, '
        '"b": {"status": "RECONCILED_EXECUTED"}, '
        '"c": {"status": "RECONCILED_NOT_EXECUTED"}}',
        encoding="utf-8",
    )
    ledger = ExecutionLedger(path)
    assert ledger.status("a") is ExecutionLedgerStatus.UNKNOWN
    assert ledger.status("b") is ExecutionLedgerStatus.UNKNOWN
    assert ledger.status("c") is ExecutionLedgerStatus.UNKNOWN


def test_legacy_accepted_without_external_id_is_not_authoritative(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(
        '{"legacy-2": "ACCEPTED", "legacy-3": "RECONCILED_EXECUTED"}',
        encoding="utf-8",
    )
    ledger = ExecutionLedger(path)
    assert ledger.status("legacy-2") is ExecutionLedgerStatus.UNKNOWN
    assert ledger.status("legacy-3") is ExecutionLedgerStatus.UNKNOWN


def test_lifecycle_second_instance_sees_new_writes(tmp_path):
    path = tmp_path / "lifecycle.json"
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)
    first.put(
        ExecutionLifecycleRecord(
            "fresh", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )
    assert second.get("fresh").state is ExecutionLifecycleState.PENDING


def test_recovery_requires_reconciliation_for_mismatches(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("reserved")
    lifecycle.put(
        ExecutionLifecycleRecord("reserved", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc))
    )
    ledger.reserve("unknown")
    ledger.mark_unknown("unknown")
    lifecycle.put(
        ExecutionLifecycleRecord("unknown", ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc))
    )
    ledger.reserve("mismatch")
    ledger.mark_accepted("mismatch", "ext")
    lifecycle.put(
        ExecutionLifecycleRecord("mismatch", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc))
    )

    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    assessment = recovery.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert {"reserved", "unknown"} <= set(assessment.unknown_request_ids)
    assert "mismatch" in assessment.unknown_request_ids or assessment.state is RecoveryState.REQUIRES_RECONCILIATION


def test_recovery_detects_ledger_without_lifecycle(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("orphan")
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    assert recovery.assess().state is RecoveryState.REQUIRES_RECONCILIATION


def test_sanctioned_composition_is_production_constructor(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    assert isinstance(
        build_real_execution_gateway(root=tmp_path, registry=registry),
        RealExecutionGateway,
    )


def test_no_direct_adapter_execute_call_outside_adapter_gateway():
    root = Path(__file__).resolve().parents[1]
    violations = []
    for path in root.rglob("*.py"):
        if path.name == "adapter_gateway.py" or path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute"
            ):
                continue
            target = ast.unparse(node.func.value).lower()
            if "adapter" in target:
                violations.append(f"{path.relative_to(root)}:{node.lineno}")
    assert violations == []


def test_real_gateway_constructed_only_by_sanctioned_composition():
    root = Path(__file__).resolve().parent
    violations = []
    for path in root.glob("*.py"):
        if path.name in {"real_gateway.py", "real_composition.py"} or path.name.startswith("test_"):
            continue
        if "RealExecutionGateway(" in path.read_text(encoding="utf-8"):
            violations.append(path.name)
    assert violations == []


def test_terminal_ledger_repairs_lifecycle_projection(tmp_path):
    gw, ledger, lifecycle = gateway(
        tmp_path, FakeAdapter(ExecutionResult(True, "accepted", "broker-repair"))
    )
    assert execute(gw, "repair-me").status == RealGatewayStatus.ADMITTED

    lifecycle_path = tmp_path / "execution-lifecycle.json"
    lifecycle_path.write_text(
        '[{"request_id":"repair-me","state":"PENDING","updated_at":"2026-09-18T00:00:00+00:00"}]',
        encoding="utf-8",
    )
    assert execute(gw, "repair-me").status == RealGatewayStatus.UNKNOWN
    gw.repair_lifecycle_projection("repair-me")
    assert lifecycle.get("repair-me").state is ExecutionLifecycleState.ACCEPTED
    assert ledger.status("repair-me") is ExecutionLedgerStatus.ACCEPTED


def test_reconciliation_requires_broker_query_and_durable_external_id(tmp_path):
    gw, ledger, lifecycle = gateway(tmp_path, FakeAdapter())
    ledger.reserve("reconcile-me")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "reconcile-me", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )

    with pytest.raises(ValueError, match="external_id durável"):
        gw.reconcile_unknown(
            "reconcile-me",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )

    ledger.attach_external_id("reconcile-me", "broker-reconcile")
    adapter = gw._gateway._registry.get("fake")
    adapter.observation = ExternalOrderObservation(
        "broker-reconcile", ExternalOrderStatus.EXECUTED, "confirmed"
    )
    gw.reconcile_unknown(
        "reconcile-me",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )
    assert adapter.query_calls == 1
    assert ledger.status("reconcile-me") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("reconcile-me").state is ExecutionLifecycleState.ACCEPTED


def test_pending_broker_observation_does_not_close_request(tmp_path):
    gw, ledger, lifecycle = gateway(tmp_path, FakeAdapter())
    ledger.reserve("pending")
    ledger.attach_external_id("pending", "broker-pending")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "pending", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )
    adapter = gw._gateway._registry.get("fake")
    adapter.observation = ExternalOrderObservation(
        "broker-pending", ExternalOrderStatus.PENDING, "still open"
    )
    with pytest.raises(ValueError, match="ainda"):
        gw.reconcile_unknown(
            "pending",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert ledger.status("pending") is ExecutionLedgerStatus.RESERVED


def test_reconciliation_lifecycle_failure_leaves_authoritative_ledger(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter(observation=ExternalOrderObservation("broker-reconciled", ExternalOrderStatus.EXECUTED, "confirmed")))
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExplodingReconcileLifecycle(lifecycle_path)
    gw = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle)
    ledger.reserve("reconcile-crash")
    ledger.attach_external_id("reconcile-crash", "broker-reconciled")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "reconcile-crash",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )

    with pytest.raises(OSError, match="lifecycle reconcile failed"):
        gw.reconcile_unknown(
            "reconcile-crash",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )


    assert ExecutionLedger(ledger_path).status("reconcile-crash") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    repaired = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    )
    repaired.repair_lifecycle_projection("reconcile-crash")
    assert ExecutionLifecycleStore(lifecycle_path).get("reconcile-crash").state is ExecutionLifecycleState.ACCEPTED


def test_real_dispatch_requires_explicit_adapter_identity(tmp_path):
    adapter = FakeAdapter()
    adapter.adapter_id = ""
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    result = gateway.execute(
        broker="fake",
        request_id="identity-missing",
        request=request(),
        authorization=auth(),
        admission=admission(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_authorization_cannot_select_different_adapter_identity(tmp_path):
    adapter = FakeAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    mismatched = RealExecutionAuthorization(
        "auth", "audit", "fake", "another-adapter", True, True
    )
    result = gateway.execute(
        broker="fake",
        request_id="identity-mismatch",
        request=request(),
        authorization=mismatched,
        admission=admission(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_demo_only_adapter_cannot_receive_real_dispatch():
    adapter = DemoOnlyAdapter()
    registry = BrokerRegistry()
    registry.register("demo", adapter)
    result = BrokerAdapterGateway(registry).execute_real(
        "demo",
        request(),
        capability=_REAL_DISPATCH_CAPABILITY,
    )
    assert result.accepted is False
    assert adapter.calls == 0


def test_ordinary_adapter_gateway_blocks_real_dispatch():
    adapter = FakeAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    result = BrokerAdapterGateway(registry).execute("fake", request())
    assert result.accepted is False
    assert adapter.calls == 0


def test_reconciliation_cannot_use_forged_boolean_or_local_result(tmp_path):
    gw, ledger, lifecycle = gateway(tmp_path, FakeAdapter())
    ledger.reserve("guard")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "guard", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )
    with pytest.raises(TypeError):
        gw.reconcile_unknown("guard", reconciliation=True)


def test_reconciliation_boundary_rejects_hand_built_observation():
    boundary = ExternalOrderReconciliationBoundary()
    with pytest.raises(TypeError):
        boundary.reconcile(
            "ext-1",
            ExternalOrderObservation("ext-1", ExternalOrderStatus.EXECUTED, "forged"),
        )
