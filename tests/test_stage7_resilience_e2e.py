from __future__ import annotations

import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

from core.decision_snapshot import DecisionSnapshot
from core.ecosystem_incidents import EcosystemIncidentManager
from core.global_operational_barrier import GlobalOperationalBarrier
from core.models import Signal
from core.operational_state import OperationalState
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionBoundary
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.risk_state_fingerprint import risk_state_identity
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from core.technical_incident_store import TechnicalIncidentStore
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class SharedMarkerAdapter:
    def __init__(self, marker_path: str):
        self.marker_path = marker_path

    def is_available(self):
        return True

    def execute(self, request):
        with open(self.marker_path, "a", encoding="utf-8") as handle:
            handle.write(request.request_id + "\n")
        return ExecutionResult(True, "accepted", "external-shared")


class StableRiskProvider:
    def __init__(self):
        self.state = OperationalState(
            balance=1000.0, equity=1000.0, realized_pnl=0.0,
            unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
            open_positions=0, net_position=0.0, exposure=0.0, market_open=True,
        )

    def current_risk_state(self):
        return self.state


class StableSafetyProvider:
    def __init__(self, report: RealSafetyReport):
        self.report = report

    def current_real_safety(self):
        return self.report


def _real_context(request_id: str):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit-shared", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    authorization = RealAuthorizationIssuer().issue(
        audit=audit, authorization_id=f"auth-{request_id}", audit_id="audit-shared",
        broker_id="fake", adapter_id="fake-adapter", request_id=request_id,
        symbol="TEST", explicit_approval=True,
    )
    admission = RealAdmissionBoundary().admit(
        admission_id=f"adm-{request_id}", audit_id="audit-shared", audit_verified=audit,
        authorization_active=authorization, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter", request_id=request_id, symbol="TEST",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=authorization.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True,
    )
    return authorization, admission, safety


def _snapshot(provider: StableRiskProvider) -> DecisionSnapshot:
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True, quality_score=90.0,
        quality_level="HIGH", actionable=True, decision="COMPRA", decision_reason="test",
        market_context=None, market_direction=None, market_score=None,
        operational_state_available=True, trades_today=0, consecutive_losses=0,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(provider.state),
    )


def _gateway_for_process(ledger_path: str, marker_path: str):
    registry = BrokerRegistry()
    registry.register("fake", SharedMarkerAdapter(marker_path), adapter_id="fake-adapter")
    ledger = ExecutionLedger(Path(ledger_path))
    provider = StableRiskProvider()
    authorization, admission, safety = _real_context("shared-process-request")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, provider, StableSafetyProvider(safety),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )
    request = ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL,
        request_id="shared-process-request", risk_state_fingerprint=risk_state_identity(provider.state),
    )
    return gateway, request, authorization, admission, safety, _snapshot(provider)


def _gateway_worker(ledger_path: str, marker_path: str, start_event, result_queue):
    start_event.wait(timeout=10)
    gateway, request, authorization, admission, safety, snapshot = _gateway_for_process(ledger_path, marker_path)
    result = gateway.execute(
        broker="fake", request_id="shared-process-request", request=request,
        authorization=authorization, admission=admission, safety=safety, snapshot=snapshot,
    )
    result_queue.put(result.status)


def test_cross_process_real_gateway_has_single_dispatch_winner(tmp_path: Path):
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    ledger_path = tmp_path / "ledger.json"
    marker_path = tmp_path / "dispatches.txt"
    processes = [
        context.Process(target=_gateway_worker, args=(str(ledger_path), str(marker_path), start_event, result_queue))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = sorted(result_queue.get(timeout=15) for _ in processes)
    for process in processes:
        process.join(timeout=15)
    assert results == [RealGatewayStatus.ADMITTED, RealGatewayStatus.BLOCKED]
    assert marker_path.read_text(encoding="utf-8").splitlines() == ["shared-process-request"]
    assert ExecutionLedger(ledger_path).status("shared-process-request") is ExecutionLedgerStatus.ACCEPTED
    assert all(process.exitcode == 0 for process in processes)


class ExternalBrokerQuery:
    def __init__(self, observation):
        self.observation = observation

    def query_order(self, external_id: str):
        return self.observation


def test_reconciliation_end_to_end_closes_unknown_and_allows_safe_recovery(tmp_path: Path):
    request_id = "req-reconcile-e2e"
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    now = datetime.now(timezone.utc)

    ledger.reserve_real(request_id, broker_id="fake", symbol="TEST")
    ledger.mark_unknown(request_id)
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now, "ambiguous broker result"))
    checkpoint.save(RuntimeCheckpoint("session-e2e", 1, request_id, now))

    from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
    observation = ExternalOrderObservation(
        external_id="external-e2e", status=ExternalOrderStatus.EXECUTED,
        message="broker confirms execution", request_id=request_id,
        evidence_source="fake-broker-query", broker_id="fake", symbol="TEST",
    )
    authority = BrokerReconciliationEvidenceAuthority(
        ExternalBrokerQuery(observation), evidence_source="fake-broker-query"
    )
    assert authority.verify(
        request_id=request_id, evidence_id="external-e2e", evidence_source="fake-broker-query",
        broker_id="fake", symbol="TEST", executed=True,
    )
    ledger.reconcile(
        request_id, executed=True, evidence_id="external-e2e", evidence_source="fake-broker-query"
    )
    lifecycle.reconcile(request_id, ExecutionLifecycleState.ACCEPTED, updated_at=now, message="reconciled")

    restarted = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
    )
    assessment = restarted.assess(session_id="session-e2e")
    assert ledger.status(request_id) is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.ACCEPTED
    assert assessment.state is RecoveryState.SAFE_TO_RESUME
    assert assessment.can_resume


def test_incident_persists_across_restart_and_recovers_without_losing_fail_closed_state(tmp_path: Path):
    store_path = tmp_path / "incident.json"
    manager = EcosystemIncidentManager(store=TechnicalIncidentStore(store_path))
    opened = manager.open_incident(
        incident_id="incident-e2e", title="Falha de execução", message="estado operacional indisponível",
        now=datetime.now(timezone.utc),
    )
    assert opened.execution_blocked
    assert manager.execution_blocked()

    restarted = EcosystemIncidentManager(store=TechnicalIncidentStore(store_path))
    assert restarted.execution_blocked()
    assert restarted.active()[0].incident_id == "incident-e2e"

    resolved = restarted.resolve_incident("incident-e2e", now=datetime.now(timezone.utc))
    assert resolved.status.value == "RESOLVED"
    final = EcosystemIncidentManager(store=TechnicalIncidentStore(store_path))
    assert not final.execution_blocked()
    assert final.active() == ()


def test_incident_state_corruption_remains_blocking_after_restart(tmp_path: Path):
    store_path = tmp_path / "incident.json"
    store_path.write_text("{broken", encoding="utf-8")
    restarted = EcosystemIncidentManager(store=TechnicalIncidentStore(store_path))
    assert restarted.execution_blocked()
    assert restarted.active()[0].incident_id == "incident-state-unavailable"
