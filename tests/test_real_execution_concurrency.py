from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p117_real_admission import RealAdmissionBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.risk_state_fingerprint import risk_state_identity
from core.global_operational_barrier import GlobalOperationalBarrier
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from execution.adapter_gateway import BrokerAdapterGateway


class CountingAdapter:
    def __init__(self, calls):
        self.calls = calls

    def is_available(self):
        return True

    def execute(self, request):
        with self.calls.get_lock():
            self.calls.value += 1
        return ExecutionResult(True, "accepted", "external-concurrency")


class CrashAfterAcceptanceAdapter:
    def __init__(self, marker: str):
        self.marker = marker

    def is_available(self):
        return True

    def execute(self, request):
        path = Path(self.marker)
        path.write_text(json.dumps({"request_id": request.request_id, "accepted": True}), encoding="utf-8")
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
        os._exit(0)


class RiskProvider:
    def current_risk_state(self):
        return _risk_state()


class SafetyProvider:
    def __init__(self, report: RealSafetyReport):
        self.report = report

    def current_real_safety(self):
        return self.report


def _risk_state() -> OperationalState:
    return OperationalState(
        balance=1000.0, equity=1000.0, realized_pnl=0.0,
        unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
        open_positions=0, net_position=0.0, exposure=0.0, market_open=True,
    )


def _snapshot() -> DecisionSnapshot:
    state = _risk_state()
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=state.trades_today, consecutive_losses=state.consecutive_losses,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(state),
    )


def _authorization(request_id: str = "REQ_PLACEHOLDER") -> object:
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAuthorizationIssuer().issue(
        audit=audit, authorization_id="auth", audit_id="audit",
        broker_id="fake", adapter_id="fake-adapter", request_id=request_id,
        symbol="TEST", explicit_approval=True,
    )


def _admission(auth=None) -> object:
    if auth is None:
        raise ValueError("auth is required for REAL admission tests")
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=audit,
        authorization_active=auth, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter",
        request_id=auth.request_id, symbol=auth.symbol,
    )


def _safety() -> RealSafetyReport:
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )


def _request(request_id: str) -> ExecutionRequest:
    return ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id,
        risk_state_fingerprint=risk_state_identity(_risk_state()),
    )


def _gateway(path: Path, adapter, verifier=None) -> RealExecutionGateway:
    registry = BrokerRegistry()
    registry.register("fake", adapter, adapter_id="fake-adapter")
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ExecutionLedger(path), RiskProvider(),
        SafetyProvider(_safety()), operational_barrier_provider=lambda: GlobalOperationalBarrier(),
        reconciliation_evidence_verifier=verifier,
    )


def _dispatch_worker(path: str, request_id: str, calls, queue) -> None:
    gateway = _gateway(Path(path), CountingAdapter(calls))
    auth = _authorization(request_id)
    result = gateway.execute(
        broker="fake", request_id=request_id, request=_request(request_id),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    queue.put(result.status)


def _reconcile_worker(path: str, request_id: str, queue) -> None:
    calls = multiprocessing.Value("i", 0)
    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(
        external_id, ExternalOrderStatus.NOT_EXECUTED, "authoritative", request_id=request_id,
        evidence_source="broker", broker_id="fake", symbol="TEST"
    )})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    gateway = _gateway(Path(path), CountingAdapter(calls), authority)
    gateway.reconcile_unknown_with_evidence(request_id, executed=False, evidence_id="evidence-" + request_id, evidence_source="broker")
    queue.put("RECONCILED")


def _crash_worker(path: str, marker: str, request_id: str) -> None:
    gateway = _gateway(Path(path), CrashAfterAcceptanceAdapter(marker))
    auth = _authorization(request_id)
    gateway.execute(
        broker="fake", request_id=request_id, request=_request(request_id),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )


def test_two_processes_same_request_id_produce_at_most_one_dispatch(tmp_path: Path):
    path = tmp_path / "ledger.json"
    calls = multiprocessing.Value("i", 0)
    queue = multiprocessing.Queue()
    ctx = multiprocessing.get_context("fork")
    processes = [
        ctx.Process(target=_dispatch_worker, args=(str(path), "same-request", calls, queue)),
        ctx.Process(target=_dispatch_worker, args=(str(path), "same-request", calls, queue)),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0

    statuses = sorted(queue.get(timeout=2) for _ in processes)
    assert calls.value == 1
    assert statuses.count(RealGatewayStatus.ADMITTED) == 1
    assert statuses.count(RealGatewayStatus.UNKNOWN) == 1 or statuses.count(RealGatewayStatus.BLOCKED) == 1
    assert ExecutionLedger(path).status("same-request") is ExecutionLedgerStatus.ACCEPTED


def test_restart_after_reserved_never_dispatches(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ExecutionLedger(path).reserve_real("reserved-before-restart", broker_id="fake", symbol="TEST")
    calls = multiprocessing.Value("i", 0)
    gateway = _gateway(path, CountingAdapter(calls))
    auth = _authorization("reserved-before-restart")
    result = gateway.execute(
        broker="fake", request_id="reserved-before-restart",
        request=_request("reserved-before-restart"), authorization=auth,
        admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status is RealGatewayStatus.UNKNOWN
    assert calls.value == 0
    assert ExecutionLedger(path).status("reserved-before-restart") is ExecutionLedgerStatus.RESERVED


def test_crash_immediately_after_broker_acceptance_leaves_reserved_and_blocks_replay(tmp_path: Path):
    path = tmp_path / "ledger.json"
    marker = tmp_path / "broker-accepted.json"
    ctx = multiprocessing.get_context("fork")
    process = ctx.Process(target=_crash_worker, args=(str(path), str(marker), "crash-after-accept"))
    process.start()
    process.join(10)
    assert process.exitcode == 0
    assert json.loads(marker.read_text(encoding="utf-8"))["accepted"] is True
    assert ExecutionLedger(path).status("crash-after-accept") is ExecutionLedgerStatus.RESERVED

    calls = multiprocessing.Value("i", 0)
    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(
        external_id, ExternalOrderStatus.NOT_EXECUTED, "authoritative", request_id="unknown-restart",
        evidence_source="broker", broker_id="fake", symbol="TEST"
    )})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    restored = _gateway(path, CountingAdapter(calls), authority)
    auth = _authorization("crash-after-accept")
    result = restored.execute(
        broker="fake", request_id="crash-after-accept",
        request=_request("crash-after-accept"), authorization=auth,
        admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status is RealGatewayStatus.UNKNOWN
    assert calls.value == 0


def test_unknown_after_restart_stays_unknown_until_explicit_reconciliation(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("unknown-restart", broker_id="fake", symbol="TEST")
    ledger.mark_unknown("unknown-restart")

    calls = multiprocessing.Value("i", 0)
    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(
        external_id, ExternalOrderStatus.NOT_EXECUTED, "authoritative", request_id="unknown-restart",
        evidence_source="broker", broker_id="fake", symbol="TEST"
    )})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    restored = _gateway(path, CountingAdapter(calls), authority)
    auth = _authorization("unknown-restart")
    result = restored.execute(
        broker="fake", request_id="unknown-restart", request=_request("unknown-restart"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status is RealGatewayStatus.UNKNOWN
    assert calls.value == 0
    assert ExecutionLedger(path).status("unknown-restart") is ExecutionLedgerStatus.UNKNOWN

    restored.reconcile_unknown_with_evidence("unknown-restart", executed=False, evidence_id="evidence-unknown-restart", evidence_source="broker")
    assert ExecutionLedger(path).status("unknown-restart") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED


def test_reconciliation_concurrent_with_dispatch_cannot_create_a_second_send(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("reconcile-race", broker_id="fake", symbol="TEST")
    ledger.mark_unknown("reconcile-race")

    calls = multiprocessing.Value("i", 0)
    queue = multiprocessing.Queue()
    ctx = multiprocessing.get_context("fork")
    dispatch = ctx.Process(target=_dispatch_worker, args=(str(path), "reconcile-race", calls, queue))
    reconcile = ctx.Process(target=_reconcile_worker, args=(str(path), "reconcile-race", queue))
    dispatch.start()
    reconcile.start()
    dispatch.join(10)
    reconcile.join(10)
    assert dispatch.exitcode == 0
    assert reconcile.exitcode == 0
    assert calls.value == 0
    statuses = {queue.get(timeout=2), queue.get(timeout=2)}
    assert "RECONCILED" in statuses
    assert RealGatewayStatus.UNKNOWN in statuses or RealGatewayStatus.BLOCKED in statuses
    assert ExecutionLedger(path).status("reconcile-race") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED


def test_reconciled_persisted_state_cannot_be_reused_for_new_send(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("reconciled", broker_id="fake", symbol="TEST")
    ledger.mark_unknown("reconciled")
    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(
        external_id, ExternalOrderStatus.NOT_EXECUTED, "authoritative", request_id="reconciled",
        evidence_source="broker", broker_id="fake", symbol="TEST"
    )})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    gateway = _gateway(path, CountingAdapter(multiprocessing.Value("i", 0)), authority)
    gateway.reconcile_unknown_with_evidence("reconciled", executed=False, evidence_id="evidence-reconciled", evidence_source="broker")

    calls = multiprocessing.Value("i", 0)
    restored = _gateway(path, CountingAdapter(calls))
    auth = _authorization("reconciled")
    result = restored.execute(
        broker="fake", request_id="reconciled", request=_request("reconciled"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert calls.value == 0


def test_real_request_cannot_enter_through_demo_port_or_provider_configuration(tmp_path: Path):
    from execution.demo_broker_port import build_ic_markets_mt5_demo_port
    from integration.execution_provider import ExecutionProviderConfigurationError, build_demo_execution_port

    port = build_ic_markets_mt5_demo_port(symbol="EURUSD")
    result = port.execute(_request("demo-to-real"))
    assert result.accepted is False

    for provider in ("real", "REAL", "real_gateway", "mt5_real", "ic_markets_mt5_real"):
        try:
            build_demo_execution_port(provider)
        except ExecutionProviderConfigurationError:
            continue
        raise AssertionError(f"REAL provider escaped DEMO configuration barrier: {provider}")
