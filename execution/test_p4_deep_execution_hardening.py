from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from multiprocessing import Process, Queue

import pytest

from core.models import Signal
from core.kill_switch import KillSwitch
from core.operation_memory import OperationMemory
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport, RealSafetyState
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary, RealAdmissionStatus
from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ReconciliationResult,
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
from execution.real_execution_locks import RealExecutionLocks


class FakeAdapter:
    supports_real_execution = True
    adapter_id = "adapter"

    def __init__(self, result: ExecutionResult | None = None, observation=None):
        self.calls = 0
        self.result = result or ExecutionResult(True, "accepted", "ext-1")
        self.observation = observation
        self.query_calls = 0
        self.request_query_calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return self.result

    def query_order_by_request_id(self, request_id):
        self.request_query_calls += 1
        if self.observation is None:
            raise ValueError("no request observation")
        return self.observation

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
        authorization_id="auth",
    )


def safety():
    return RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True, authorization_id=auth().authorization_id,
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


def test_unknown_persistence_failure_is_explicitly_reported(tmp_path):
    adapter = FakeAdapter()
    def fail_execute(request):
        adapter.calls += 1
        raise RuntimeError("transport timeout after send")
    adapter.execute = fail_execute
    gw, ledger, lifecycle = gateway(tmp_path, adapter)

    def fail_mark_unknown(request_id):
        raise OSError("ledger unavailable")
    ledger.mark_unknown = fail_mark_unknown

    result = execute(gw, "unknown-persistence")

    assert result.status == RealGatewayStatus.UNKNOWN
    assert "persistência de estado incerto também falhou" in result.message
    assert "Ledger: ledger unavailable" in result.message
    assert adapter.calls == 1


def test_real_boundary_rejects_wrong_context_object_types(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())
    result = gw.execute(
        broker="fake",
        request_id="types",
        request=request("types"),
        authorization=object(),
        admission=admission(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED

    result = gw.execute(
        broker="fake",
        request_id="types-2",
        request=request("types-2"),
        authorization=auth(),
        admission=object(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED

    result = gw.execute(
        broker="fake",
        request_id="types-3",
        request=request("types-3"),
        authorization=auth(),
        admission=admission(),
        safety=object(),
    )
    assert result.status == RealGatewayStatus.BLOCKED


def test_real_gateway_blocks_aguardar_and_boolean_amount(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())
    aguardando = ExecutionRequest("TEST", Signal.AGUARDAR, 1.0, 60, ExecutionMode.REAL, request_id="wait")
    result = gw.execute(
        broker="fake", request_id="wait", request=aguardando,
        authorization=auth(), admission=admission(), safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED

    invalid_amount = ExecutionRequest("TEST", Signal.COMPRA, True, 60, ExecutionMode.REAL, request_id="bool")
    result = gw.execute(
        broker="fake", request_id="bool", request=invalid_amount,
        authorization=auth(), admission=admission(), safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED


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
        authorization_id="auth",
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
    lifecycle = ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
    original_put = lifecycle.put
    def fail_accepted(record):
        if record.state is ExecutionLifecycleState.ACCEPTED:
            raise OSError("lifecycle write failed")
        return original_put(record)
    lifecycle.put = fail_accepted
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
    class LegacyQueryOnlyAdapter(FakeAdapter):
        query_order_by_request_id = None

    gw, ledger, lifecycle = gateway(tmp_path, LegacyQueryOnlyAdapter())
    ledger.reserve("reconcile-me")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "reconcile-me", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )

    with pytest.raises(ValueError, match="sem external_id"):
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
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    original_reconcile = lifecycle.reconcile
    def fail_reconcile(*args, **kwargs):
        raise OSError("lifecycle reconcile failed")
    lifecycle.reconcile = fail_reconcile
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

    with pytest.raises(ValueError, match="Ledger reconciliado, mas projeção Lifecycle falhou"):
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
        request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="identity-missing"),
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
    result = BrokerAdapterGateway(registry)._execute_real(
        "demo",
        request(),
        capability=_REAL_DISPATCH_CAPABILITY,
        request_id=request().request_id,
        authorization_id="test-auth",
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


class MutatingQueryAdapter(FakeAdapter):
    def __init__(self, *, mutate_mode: str, registry=None):
        super().__init__(observation=ExternalOrderObservation("broker-mut", ExternalOrderStatus.EXECUTED, "confirmed"))
        self.mutate_mode = mutate_mode
        self.registry = registry

    def query_order(self, external_id):
        result = super().query_order(external_id)
        if self.mutate_mode == "identity":
            self.adapter_id = "mutated"
        elif self.mutate_mode == "capability":
            self.supports_real_execution = False
        elif self.mutate_mode == "replacement":
            replacement = FakeAdapter(observation=self.observation)
            replacement.adapter_id = self.adapter_id
            self.registry._adapters["fake"] = replacement
        return result


@pytest.mark.parametrize("mutation", ["identity", "capability", "replacement"])
def test_reconciliation_revalidates_query_capability_after_broker_call(tmp_path, mutation):
    registry = BrokerRegistry()
    adapter = MutatingQueryAdapter(mutate_mode=mutation, registry=registry)
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gw = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle)
    ledger.reserve("query-mutation")
    ledger.attach_external_id("query-mutation", "broker-mut")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "query-mutation", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )

    with pytest.raises(ValueError, match="capacidade de consulta REAL mudou"):
        gw.reconcile_unknown(
            "query-mutation",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert ledger.status("query-mutation") is ExecutionLedgerStatus.RESERVED


def test_reconciliation_boundary_rejects_hand_built_observation():
    boundary = ExternalOrderReconciliationBoundary()
    with pytest.raises(TypeError):
        boundary.reconcile(
            "ext-1",
            ExternalOrderObservation("ext-1", ExternalOrderStatus.EXECUTED, "forged"),
        )


def test_reconciliation_repairs_ledger_unknown_lifecycle_pending_mismatch(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-reconcile", ExternalOrderStatus.EXECUTED, "confirmed"
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("projection-mismatch")
    ledger.attach_external_id("projection-mismatch", "broker-reconcile")
    ledger.mark_unknown("projection-mismatch")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "projection-mismatch",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )
    gw.reconcile_unknown(
        "projection-mismatch",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )
    assert ledger.status("projection-mismatch") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("projection-mismatch").state is ExecutionLifecycleState.ACCEPTED

def test_repair_lifecycle_projection_can_recreate_missing_projection(tmp_path):
    gw, ledger, lifecycle = gateway(
        tmp_path, FakeAdapter(ExecutionResult(True, "accepted", "broker-repair-missing"))
    )
    result = execute(gw, "repair-missing")
    assert result.status == RealGatewayStatus.ADMITTED
    lifecycle_path = tmp_path / "execution-lifecycle.json"
    lifecycle_path.unlink()
    assert lifecycle.get("repair-missing") is None

    gw.repair_lifecycle_projection("repair-missing")
    assert ExecutionLifecycleStore(lifecycle_path).get("repair-missing").state is ExecutionLifecycleState.ACCEPTED
    assert ledger.status("repair-missing") is ExecutionLedgerStatus.ACCEPTED


# REAL lock acquisition must fail closed at the domain boundary rather than
# leaking a raw OSError out of the execution orchestration layer.
def test_real_lock_converts_fcntl_acquisition_failure_to_domain_error(tmp_path, monkeypatch):
    import execution.real_execution_locks as lock_module
    from execution.real_execution_locks import RealExecutionLockError, RealExecutionLocks

    class BrokenFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(_fd, operation):
            if operation == BrokenFcntl.LOCK_EX:
                raise OSError("simulated flock failure")

    monkeypatch.setattr(lock_module, "fcntl", BrokenFcntl)
    monkeypatch.setattr(lock_module, "msvcrt", None)
    with pytest.raises(RealExecutionLockError, match="simulated flock failure"):
        with RealExecutionLocks(tmp_path / "ledger.json").acquire("lock-failure"):
            pass


def test_real_lock_still_rejects_when_no_interprocess_lock_exists(tmp_path, monkeypatch):
    import execution.real_execution_locks as lock_module
    from execution.real_execution_locks import RealExecutionLockError, RealExecutionLocks

    monkeypatch.setattr(lock_module, "fcntl", None)
    monkeypatch.setattr(lock_module, "msvcrt", None)
    with pytest.raises(RealExecutionLockError, match="lock interprocesso"):
        with RealExecutionLocks(tmp_path / "ledger.json").acquire("no-lock"):
            pass


def test_real_boundary_rejects_mutated_authorization_identity_fields(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())
    malformed = auth()
    object.__setattr__(malformed, "broker_id", None)
    result = gw.execute(
        broker="fake",
        request_id="malformed-auth",
        request=request("malformed-auth"),
        authorization=malformed,
        admission=admission(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED
    assert "broker_id" in result.message


def test_real_capability_rejects_truthy_non_boolean_flag(tmp_path):
    adapter = FakeAdapter()
    adapter.supports_real_execution = "true"
    gw, _, _ = gateway(tmp_path, adapter)
    result = execute(gw, "truthy-capability")
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_authorization_rejects_truthy_non_boolean_flags(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())
    malformed = auth()
    object.__setattr__(malformed, "real_execution_allowed", "false")
    result = gw.execute(
        broker="fake",
        request_id="truthy-auth",
        request=request("truthy-auth"),
        authorization=malformed,
        admission=admission(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.BLOCKED


def test_real_gateway_execute_fails_closed_when_lock_acquisition_breaks(tmp_path, monkeypatch):
    import execution.real_execution_locks as lock_module

    gw, _, _ = gateway(tmp_path, FakeAdapter())

    class BrokenFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(_fd, operation):
            if operation == BrokenFcntl.LOCK_EX:
                raise OSError("simulated gateway lock failure")

    monkeypatch.setattr(lock_module, "fcntl", BrokenFcntl)
    monkeypatch.setattr(lock_module, "msvcrt", None)
    result = execute(gw, "gateway-lock-failure")
    assert result.status == RealGatewayStatus.BLOCKED
    assert "lock de execução indisponível" in result.message


def test_real_reconciliation_fails_closed_when_lock_acquisition_breaks(tmp_path, monkeypatch):
    import execution.real_execution_locks as lock_module

    gw, ledger, lifecycle = gateway(tmp_path, FakeAdapter())
    ledger.reserve("reconcile-lock-failure")
    ledger.attach_external_id("reconcile-lock-failure", "broker-reconcile")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "reconcile-lock-failure",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )

    class BrokenFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(_fd, operation):
            if operation == BrokenFcntl.LOCK_EX:
                raise OSError("simulated reconciliation lock failure")

    monkeypatch.setattr(lock_module, "fcntl", BrokenFcntl)
    monkeypatch.setattr(lock_module, "msvcrt", None)
    with pytest.raises(ValueError, match="lock de reconciliação indisponível"):
        gw.reconcile_unknown(
            "reconcile-lock-failure",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert ledger.status("reconcile-lock-failure") is ExecutionLedgerStatus.RESERVED


def test_real_gateway_rejects_overridable_dependency_subclasses(tmp_path):
    class GatewayOverride(BrokerAdapterGateway):
        def execute_real(self, *args, **kwargs):
            raise AssertionError("override must never be trusted by REAL boundary")

    class LedgerOverride(ExecutionLedger):
        pass

    class LifecycleOverride(ExecutionLifecycleStore):
        pass

    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    base_gateway = BrokerAdapterGateway(registry)
    with pytest.raises(ValueError, match="adapter_gateway inválido"):
        RealExecutionGateway(GatewayOverride(registry), ExecutionLedger(tmp_path / "ledger.json"))
    with pytest.raises(ValueError, match="ledger é obrigatório"):
        RealExecutionGateway(base_gateway, LedgerOverride(tmp_path / "ledger-override.json"))
    with pytest.raises(ValueError, match="lifecycle inválido"):
        RealExecutionGateway(
            base_gateway,
            ExecutionLedger(tmp_path / "ledger.json"),
            LifecycleOverride(tmp_path / "lifecycle-override.json"),
        )


def test_adapter_gateway_rejects_overridable_registry_subclass():
    class RegistryOverride(BrokerRegistry):
        def get(self, name):
            raise AssertionError("registry override must not cross REAL gateway boundary")

    with pytest.raises(ValueError, match="registry inválido"):
        BrokerAdapterGateway(RegistryOverride())


class MaliciousReconciliationBoundary(ExternalOrderReconciliationBoundary):
    def reconcile(self, external_id, *, query_port):
        return ReconciliationResult(
            external_id=external_id,
            status=ExternalOrderStatus.EXECUTED,
            reconciled=True,
            message="forged terminal evidence",
        )


def test_real_reconciliation_rejects_overridable_boundary_subclass(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())
    with pytest.raises(ValueError, match="boundary de reconciliação inválida"):
        gw.reconcile_unknown(
            "missing",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=MaliciousReconciliationBoundary(),
        )



class MaliciousAuthorization(RealExecutionAuthorization):
    @property
    def active(self):
        return True


class MaliciousAdmission(RealAdmission):
    @property
    def admitted(self):
        return True


class MaliciousSafetyReport(RealSafetyReport):
    @property
    def ready(self):
        return True


def test_real_boundary_rejects_overridable_policy_context_subclasses(tmp_path):
    gw, _, _ = gateway(tmp_path, FakeAdapter())

    malicious_auth = MaliciousAuthorization("auth", "audit", "fake", "adapter", True, True)
    malicious_admission = MaliciousAdmission(
        admission_id="adm",
        audit_id="audit",
        status=RealAdmissionStatus.BLOCKED,
        broker_id="fake",
        authorization_id="auth",
        reasons=("blocked",),
    )
    malicious_safety = MaliciousSafetyReport(
        state=RealSafetyState.BLOCKED,
        authorization_id="auth",
        reasons=("blocked",),
    )

    result = gw.execute(
        broker="fake",
        request_id="sub-auth",
        request=request("sub-auth"),
        authorization=malicious_auth,
        admission=admission(),
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED

    result = gw.execute(
        broker="fake",
        request_id="sub-admission",
        request=request("sub-admission"),
        authorization=auth(),
        admission=malicious_admission,
        safety=safety(),
    )
    assert result.status == RealGatewayStatus.REJECTED

    result = gw.execute(
        broker="fake",
        request_id="sub-safety",
        request=request("sub-safety"),
        authorization=auth(),
        admission=admission(),
        safety=malicious_safety,
    )
    assert result.status == RealGatewayStatus.BLOCKED



def test_reservation_survives_pending_projection_failure_without_dispatch(tmp_path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
    original_put = lifecycle.put
    def fail_pending(record):
        if record.state is ExecutionLifecycleState.PENDING:
            raise OSError("pending lifecycle write failed")
        return original_put(record)
    lifecycle.put = fail_pending
    gw = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle)

    result = execute(gw, "pending-write-failure")

    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ledger.status("pending-write-failure") is ExecutionLedgerStatus.RESERVED


def test_external_id_attached_before_acceptance_failure_remains_reconcilable(tmp_path):
    gw, ledger, lifecycle = gateway(
        tmp_path, FakeAdapter(ExecutionResult(True, "accepted", "broker-attach-failure"))
    )
    original = ledger.mark_accepted

    def fail_mark_accepted(request_id, external_id=None):
        raise OSError("accepted state write failed")

    ledger.mark_accepted = fail_mark_accepted
    result = execute(gw, "attach-failure")
    ledger.mark_accepted = original

    assert result.status == RealGatewayStatus.UNKNOWN
    entry = ledger.entry("attach-failure")
    assert entry.status is ExecutionLedgerStatus.RESERVED
    assert entry.external_id == "broker-attach-failure"
    assert lifecycle.get("attach-failure").state is ExecutionLifecycleState.PENDING


def test_reconciliation_keeps_ledger_terminal_when_lifecycle_projection_fails(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-reconcile-failure",
            ExternalOrderStatus.EXECUTED,
            "filled",
        )
    )
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")
    ledger.reserve("reconcile-lifecycle-failure")
    ledger.attach_external_id("reconcile-lifecycle-failure", "broker-reconcile-failure")
    ledger.mark_unknown("reconcile-lifecycle-failure")
    lifecycle = ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json")
    original_reconcile = lifecycle.reconcile
    def fail_reconcile(*args, **kwargs):
        raise OSError("lifecycle reconcile failed")
    lifecycle.reconcile = fail_reconcile
    lifecycle.put(
        ExecutionLifecycleRecord(
            "reconcile-lifecycle-failure",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
        )
    )
    gw = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle)

    with pytest.raises(ValueError, match="Ledger reconciliado"):
        gw.reconcile_unknown(
            "reconcile-lifecycle-failure",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )

    assert ledger.status("reconcile-lifecycle-failure") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("reconcile-lifecycle-failure").state is ExecutionLifecycleState.UNKNOWN
    lifecycle.reconcile = original_reconcile
    gw.repair_lifecycle_projection("reconcile-lifecycle-failure")
    assert lifecycle.get("reconcile-lifecycle-failure").state is ExecutionLifecycleState.ACCEPTED


def test_execute_real_is_called_only_by_real_gateway_source():
    root = Path(__file__).resolve().parents[1]
    violations = []
    for path in root.rglob("*.py"):
        if path.name.startswith("test_") or path.name == "real_gateway.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"execute_real", "_execute_real", "real_dispatch_capability", "_real_dispatch_capability"}
            ):
                violations.append(f"{path.relative_to(root)}:{node.lineno}")
    assert violations == []


def test_ledger_normalizes_external_id_and_rejects_non_boolean_reconciliation(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("normalize")
    ledger.attach_external_id("normalize", "  broker-123  ")
    assert ledger.external_id("normalize") == "broker-123"
    ledger.mark_unknown("normalize")
    ledger.reconcile("normalize", executed=False, external_id="  broker-123  ")
    assert ledger.external_id("normalize") == "broker-123"
    assert ledger.status("normalize") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED

    ledger.reserve("strict-bool")
    ledger.attach_external_id("strict-bool", "broker-456")
    ledger.mark_unknown("strict-bool")
    with pytest.raises(ValueError, match="executed precisa ser booleano"):
        ledger.reconcile("strict-bool", executed="false", external_id="broker-456")


def test_ledger_refresh_clears_stale_snapshot_when_file_is_removed(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("stale-id")
    assert ledger.contains("stale-id")

    path.unlink()

    assert ledger.status("stale-id") is None
    assert ledger.records() == ()


def test_ledger_rejects_duplicate_request_ids_in_legacy_list(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('["dup", "dup"]', encoding="utf-8")
    with pytest.raises(ValueError, match="request_id duplicado"):
        ExecutionLedger(path)


def test_ledger_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(
        '{"dup": {"status": "RESERVED"}, "dup": {"status": "UNKNOWN"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="chave duplicada"):
        ExecutionLedger(path)



def test_lifecycle_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(
        '[{"request_id": "dup", "request_id": "other", "state": "UNKNOWN", '
        '"updated_at": "2026-09-18T00:00:00+00:00"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)


def test_reconciliation_repairs_partial_unknown_lifecycle_projection(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-reconcile", ExternalOrderStatus.EXECUTED, "confirmed"
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("projection-mismatch")
    ledger.attach_external_id("projection-mismatch", "broker-reconcile")
    ledger.mark_unknown("projection-mismatch")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "projection-mismatch",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )

    gw.reconcile_unknown(
        "projection-mismatch",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )

    assert ledger.status("projection-mismatch") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("projection-mismatch").state is ExecutionLifecycleState.ACCEPTED


def test_reconciliation_recreates_missing_lifecycle_projection(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-reconcile", ExternalOrderStatus.EXECUTED, "confirmed"
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("missing-projection")
    ledger.attach_external_id("missing-projection", "broker-reconcile")
    ledger.mark_unknown("missing-projection")
    lifecycle_path = tmp_path / "execution-lifecycle.json"
    if lifecycle_path.exists():
        lifecycle_path.unlink()

    gw.reconcile_unknown(
        "missing-projection",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )

    assert ledger.status("missing-projection") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ExecutionLifecycleStore(lifecycle_path).get("missing-projection").state is ExecutionLifecycleState.ACCEPTED


def test_reconciliation_repairs_reserved_lifecycle_unknown_with_durable_external_id(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-reconcile", ExternalOrderStatus.EXECUTED, "confirmed"
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("reserved-projection")
    ledger.attach_external_id("reserved-projection", "broker-reconcile")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "reserved-projection",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
        )
    )

    gw.reconcile_unknown(
        "reserved-projection",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )

    assert ledger.status("reserved-projection") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("reserved-projection").state is ExecutionLifecycleState.ACCEPTED


def test_reconciliation_is_blocked_by_persistent_kill_switch_before_broker_query(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-reconcile", ExternalOrderStatus.EXECUTED, "confirmed", "kill-switch-recovery"
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("kill-switch-recovery")
    lifecycle.put(ExecutionLifecycleRecord(
        "kill-switch-recovery", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
    ))
    gw._kill_switch.activate("recovery emergency stop")

    with pytest.raises(ValueError, match="kill switch"):
        gw.reconcile_unknown(
            "kill-switch-recovery",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )

    assert adapter.calls == 0
    assert adapter.request_query_calls == 0
    assert ledger.status("kill-switch-recovery") is ExecutionLedgerStatus.RESERVED

def test_recovery_can_find_broker_acceptance_by_request_reference_without_external_id(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-after-crash", ExternalOrderStatus.EXECUTED, "accepted before crash",
            "crash-no-external-id",
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("crash-no-external-id")
    lifecycle.put(ExecutionLifecycleRecord(
        "crash-no-external-id", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
    ))

    gw.reconcile_unknown(
        "crash-no-external-id",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )

    assert adapter.calls == 0
    assert adapter.request_query_calls == 1
    assert ledger.status("crash-no-external-id") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ledger.external_id("crash-no-external-id") == "broker-after-crash"
    assert lifecycle.get("crash-no-external-id").state is ExecutionLifecycleState.ACCEPTED


def test_recovery_does_not_retry_when_request_reference_is_pending(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-pending", ExternalOrderStatus.PENDING, "still pending",
            "crash-pending",
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("crash-pending")
    lifecycle.put(ExecutionLifecycleRecord(
        "crash-pending", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
    ))

    with pytest.raises(ValueError, match="evidência terminal"):
        gw.reconcile_unknown(
            "crash-pending", broker="fake", authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert adapter.calls == 0
    assert ledger.status("crash-pending") is ExecutionLedgerStatus.RESERVED


def test_request_reference_query_rejects_broker_observation_for_another_request(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-wrong", ExternalOrderStatus.EXECUTED, "wrong order",
            "another-request",
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("requested-order")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "requested-order", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
        )
    )

    with pytest.raises(ValueError, match="outro request_id"):
        gw.reconcile_unknown(
            "requested-order",
            broker="fake",
            authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert adapter.calls == 0
    assert ledger.status("requested-order") is ExecutionLedgerStatus.RESERVED


def test_request_reference_query_is_pinned_to_real_adapter_identity(tmp_path):
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "broker-after-crash", ExternalOrderStatus.EXECUTED, "accepted",
            "pinned-query",
        )
    )
    gw, ledger, lifecycle = gateway(tmp_path, adapter)
    ledger.reserve("pinned-query")
    lifecycle.put(ExecutionLifecycleRecord(
        "pinned-query", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)
    ))
    original = adapter.query_order_by_request_id
    def mutate_then_return(request_id):
        adapter.adapter_id = "changed"
        return original(request_id)
    adapter.query_order_by_request_id = mutate_then_return

    with pytest.raises(ValueError, match="capacidade de consulta por request_id mudou"):
        gw.reconcile_unknown(
            "pinned-query", broker="fake", authorization=auth(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert ledger.status("pinned-query") is ExecutionLedgerStatus.RESERVED
    assert adapter.calls == 0


def test_real_composition_creates_shared_persistent_kill_switch(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    gateway = build_real_execution_gateway(root=tmp_path, registry=registry)

    switch_path = tmp_path / "real-kill-switch.json"
    assert switch_path.exists()

    switch = KillSwitch(switch_path)
    switch.activate("global emergency stop")

    result = execute(gateway, "composition-kill")
    assert result.status == RealGatewayStatus.BLOCKED
    assert registry.get("fake").calls == 0


def test_real_composition_rejects_nonpersistent_kill_switch(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())

    with pytest.raises(ValueError, match="kill switch persistente"):
        build_real_execution_gateway(
            root=tmp_path,
            registry=registry,
            kill_switch=KillSwitch(),
        )


def test_real_gateway_rejects_in_memory_kill_switch_side_door(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    ledger = ExecutionLedger(tmp_path / "execution-ledger.json")

    with pytest.raises(ValueError, match="kill switch persistente"):
        RealExecutionGateway(
            BrokerAdapterGateway(registry),
            ledger,
            ExecutionLifecycleStore(tmp_path / "execution-lifecycle.json"),
            KillSwitch(),
        )


def test_real_composition_binds_kill_switch_to_same_global_execution_barrier(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    gateway = build_real_execution_gateway(root=tmp_path, registry=registry)

    expected = RealExecutionLocks(tmp_path / "execution-ledger.json").global_lock_path
    kill_switch = gateway._kill_switch

    assert kill_switch._path == tmp_path / "real-kill-switch.json"
    assert kill_switch._coordination_lock_path == expected


def test_real_admission_artifact_rejects_inconsistent_manual_construction():
    with pytest.raises(ValueError, match="ADMITTED"):
        RealAdmission(
            admission_id="adm",
            audit_id="audit",
            status=RealAdmissionStatus.ADMITTED,
            broker_id="fake",
            authorization_id="auth",
            reasons=("forged blocked reason",),
        )
    with pytest.raises(ValueError, match="BLOCKED"):
        RealAdmission(
            admission_id="adm",
            audit_id="audit",
            status=RealAdmissionStatus.BLOCKED,
            broker_id="fake",
            authorization_id="auth",
            reasons=(),
        )


def test_real_safety_artifact_rejects_inconsistent_manual_construction():
    with pytest.raises(ValueError, match="READY"):
        RealSafetyReport(
            state=RealSafetyState.READY,
            authorization_id="auth",
            reasons=("forged blocked reason",),
        )
    with pytest.raises(ValueError, match="BLOCKED"):
        RealSafetyReport(
            state=RealSafetyState.BLOCKED,
            authorization_id="auth",
            reasons=(),
        )


def test_real_authorization_rejects_noncanonical_identity_fields():
    with pytest.raises(ValueError, match="canônico"):
        RealExecutionAuthorization(
            " auth", "audit", "fake", "adapter", True, True
        )
    with pytest.raises(ValueError, match="canônico"):
        RealExecutionAuthorization(
            "auth", "audit", "fake", "adapter ", True, True
        )


def test_real_gateway_rejects_cross_bound_authorization_provenance(tmp_path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
    )
    auth = RealExecutionAuthorization("auth-a", "audit-a", "fake", "fake-adapter", True, True)
    other = RealExecutionAuthorization("auth-b", "audit-b", "fake", "fake-adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id=auth.audit_id, audit_verified=True,
        authorization_active=auth.active, safety_ready=True,
        broker_available=True, broker_id="fake", authorization_id=other.authorization_id,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True, authorization_id=other.authorization_id,
    )
    result = gateway.execute(
        broker="fake", request_id="cross-bound",
        request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="cross-bound"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status == RealGatewayStatus.REJECTED
    assert adapter.calls == 0
