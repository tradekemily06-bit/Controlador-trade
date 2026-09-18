from __future__ import annotations

import multiprocessing
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
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class CountingAdapter:
    def __init__(self, calls):
        self.calls = calls

    def is_available(self):
        return True

    def execute(self, request):
        with self.calls.get_lock():
            self.calls.value += 1
        return ExecutionResult(True, "accepted", "external-recovery-matrix")


class RiskProvider:
    def current_risk_state(self):
        return OperationalState(
            balance=1000.0, equity=1000.0, realized_pnl=0.0,
            unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
            open_positions=0, net_position=0.0, exposure=0.0, market_open=True,
        )


class SafetyProvider:
    def current_real_safety(self):
        return RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True,
            market_healthy=True, recovery_safe=True,
            risk_approved=True, broker_available=True,
        )


class CrashBeforeMarkAcceptedLedger(ExecutionLedger):
    def mark_accepted_real(self, request_id: str, *, external_id: str) -> None:
        raise OSError("simulated process death before mark_accepted_real")


def _state() -> OperationalState:
    return RiskProvider().current_risk_state()


def _snapshot() -> DecisionSnapshot:
    state = _state()
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=state.trades_today, consecutive_losses=state.consecutive_losses,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(state),
    )


def _authorization(request_id: str = "REQ_PLACEHOLDER"):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAuthorizationIssuer().issue(
        audit=audit, authorization_id="auth", audit_id="audit",
        broker_id="fake", adapter_id="fake-adapter", request_id=request_id,
        symbol="TEST", explicit_approval=True,
    )


def _admission(auth=None):
    auth = auth or _authorization()
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
        market_healthy=True, recovery_safe=True,
        risk_approved=True, broker_available=True,
    )


def _request(request_id: str) -> ExecutionRequest:
    return ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id,
        risk_state_fingerprint=risk_state_identity(_state()),
    )


def _gateway(path: Path, calls, verifier=None) -> RealExecutionGateway:
    registry = BrokerRegistry()
    registry.register("fake", CountingAdapter(calls), adapter_id="fake-adapter")
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ExecutionLedger(path),
        RiskProvider(), SafetyProvider(), operational_barrier_provider=lambda: GlobalOperationalBarrier(),
        reconciliation_evidence_verifier=verifier,
    )


def _dispatch(path: str, request_id: str, calls, queue) -> None:
    gateway = _gateway(Path(path), calls)
    auth = _authorization(request_id)
    result = gateway.execute(
        broker="fake", request_id=request_id, request=_request(request_id),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    queue.put(result.status)


def _reconcile(path: str, request_id: str, queue) -> None:
    calls = multiprocessing.Value("i", 0)
    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(
        external_id, ExternalOrderStatus.NOT_EXECUTED, "authoritative", request_id=request_id,
        evidence_source="broker", broker_id="fake", symbol="TEST"
    )})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    gateway = _gateway(Path(path), calls, authority)
    gateway.reconcile_unknown_with_evidence(request_id, executed=False, evidence_id="evidence-" + request_id, evidence_source="broker")
    queue.put("RECONCILED")


def test_reserved_dispatch_and_reconciliation_race_never_sends(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ExecutionLedger(path).reserve_real("reserved-race", broker_id="fake", symbol="TEST")
    calls = multiprocessing.Value("i", 0)
    queue = multiprocessing.Queue()
    ctx = multiprocessing.get_context("fork")
    processes = [
        ctx.Process(target=_dispatch, args=(str(path), "reserved-race", calls, queue)),
        ctx.Process(target=_reconcile, args=(str(path), "reserved-race", queue)),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0

    statuses = {queue.get(timeout=2), queue.get(timeout=2)}
    assert calls.value == 0
    assert "RECONCILED" in statuses
    assert RealGatewayStatus.UNKNOWN in statuses or RealGatewayStatus.BLOCKED in statuses
    assert ExecutionLedger(path).status("reserved-race") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED


def test_accepted_request_remains_terminal_across_restart_and_cannot_send_again(tmp_path: Path):
    path = tmp_path / "ledger.json"
    calls = multiprocessing.Value("i", 0)
    first = _gateway(path, calls)
    auth = _authorization("terminal-restart")
    first_result = first.execute(
        broker="fake", request_id="terminal-restart", request=_request("terminal-restart"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert first_result.status is RealGatewayStatus.ADMITTED
    assert calls.value == 1

    restored_calls = multiprocessing.Value("i", 0)
    restored = _gateway(path, restored_calls)
    auth = _authorization("terminal-restart")
    second_result = restored.execute(
        broker="fake", request_id="terminal-restart", request=_request("terminal-restart"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert second_result.status is RealGatewayStatus.BLOCKED
    assert restored_calls.value == 0
    assert ExecutionLedger(path).status("terminal-restart") is ExecutionLedgerStatus.ACCEPTED


def test_reconciled_executed_state_is_terminal_and_never_resubmits(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("reconciled-executed", broker_id="fake", symbol="TEST")
    ledger.mark_unknown("reconciled-executed")
    calls = multiprocessing.Value("i", 0)
    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(
        external_id, ExternalOrderStatus.EXECUTED, "authoritative", request_id="reconciled-executed", evidence_source="broker", broker_id="fake", symbol="TEST"
    )})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    gateway = _gateway(path, calls, authority)
    gateway.reconcile_unknown_with_evidence("reconciled-executed", executed=True, evidence_id="evidence-reconciled-executed", evidence_source="broker")

    restored_calls = multiprocessing.Value("i", 0)
    restored = _gateway(path, restored_calls)
    auth = _authorization("reconciled-executed")
    result = restored.execute(
        broker="fake", request_id="reconciled-executed", request=_request("reconciled-executed"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert restored_calls.value == 0
    assert ExecutionLedger(path).status("reconciled-executed") is ExecutionLedgerStatus.RECONCILED_EXECUTED


def test_external_acceptance_process_death_restart_reconcile_and_replay_are_all_closed(tmp_path: Path):
    path = tmp_path / "ledger.json"
    calls = multiprocessing.Value("i", 0)
    registry = BrokerRegistry()
    registry.register("fake", CountingAdapter(calls), adapter_id="fake-adapter")
    crashed = RealExecutionGateway(
        BrokerAdapterGateway(registry), CrashBeforeMarkAcceptedLedger(path),
        RiskProvider(), SafetyProvider(), operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )

    auth = _authorization("crash-window")
    first = crashed.execute(
        broker="fake", request_id="crash-window", request=_request("crash-window"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert first.status is RealGatewayStatus.UNKNOWN
    assert calls.value == 1
    assert ExecutionLedger(path).status("crash-window") is ExecutionLedgerStatus.RESERVED

    restored_calls = multiprocessing.Value("i", 0)
    restored = _gateway(path, restored_calls)
    auth = _authorization("crash-window")
    after_restart = restored.execute(
        broker="fake", request_id="crash-window", request=_request("crash-window"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert after_restart.status is RealGatewayStatus.UNKNOWN
    assert restored_calls.value == 0

    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(
        external_id, ExternalOrderStatus.EXECUTED, "authoritative", request_id="crash-window", evidence_source="broker", broker_id="fake", symbol="TEST"
    )})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    restored = _gateway(path, restored_calls, authority)
    restored.reconcile_unknown_with_evidence("crash-window", executed=True, evidence_id="evidence-crash-window", evidence_source="broker")
    assert ExecutionLedger(path).status("crash-window") is ExecutionLedgerStatus.RECONCILED_EXECUTED

    final_calls = multiprocessing.Value("i", 0)
    final_gateway = _gateway(path, final_calls)
    auth = _authorization("crash-window")
    replay = final_gateway.execute(
        broker="fake", request_id="crash-window", request=_request("crash-window"),
        authorization=auth, admission=_admission(auth), safety=_safety(), snapshot=_snapshot(),
    )
    assert replay.status is RealGatewayStatus.BLOCKED
    assert final_calls.value == 0
    assert calls.value == 1
