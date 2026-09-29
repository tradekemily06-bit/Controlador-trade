from datetime import datetime, timezone

from integration.ecosystem_service import EcosystemService
from core.operational_runtime import build_operational_runtime
from core.operation_lineage import OperationLineage
from core.operation_context_store import OperationContextStore
from core.decision_snapshot import DecisionSnapshot
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState


def test_shared_runtime_starts_fail_closed_and_exposes_authoritative_state(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)

    snapshot = service.operational_observability()

    assert runtime.gateway._kill_switch is runtime.kill_switch
    assert runtime.gateway._ledger is runtime.execution_ledger
    assert runtime.gateway._lifecycle is runtime.execution_lifecycle
    assert snapshot["execution"] == {
        "allowed": False,
        "mode": "DEMO",
        "state": "BLOCKED",
        "real": "DISABLED",
    }
    assert snapshot["recovery"]["state"] == "FRESH"
    assert snapshot["recovery"]["can_resume"] is True
    assert snapshot["kill_switch"]["state"] == "CLEAR"
    assert snapshot["runtime_health"]["state"] == "HEALTHY"
    assert snapshot["market_data"]["health"] == "NOT_CONNECTED"


def test_pending_runtime_is_visible_and_blocks_operation(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord("req-pending", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc))
    )

    snapshot = service.operational_observability()

    assert snapshot["execution"]["state"] == "BLOCKED"
    assert snapshot["reconciliation"]["state"] == "REQUIRED"
    assert snapshot["reconciliation"]["pending_request_ids"] == ["req-pending"]
    assert snapshot["recovery"]["can_resume"] is False
    assert snapshot["runtime_health"]["state"] == "ATTENTION"


def test_unknown_runtime_is_critical_to_operation_and_surfaces_id(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord("req-unknown", ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc))
    )

    snapshot = service.operational_observability()

    assert snapshot["execution"]["state"] == "BLOCKED"
    assert snapshot["reconciliation"]["state"] == "REQUIRED"
    assert snapshot["reconciliation"]["unknown_request_ids"] == ["req-unknown"]
    assert snapshot["runtime_health"]["state"] == "BLOCKED"


def test_kill_switch_is_shared_and_blocks_operation(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    runtime.kill_switch.activate("teste de segurança")

    snapshot = service.operational_observability()

    assert runtime.gateway._kill_switch is runtime.kill_switch
    assert snapshot["execution"]["state"] == "BLOCKED"
    assert snapshot["kill_switch"] == {
        "state": "ACTIVE",
        "enabled": True,
        "reason": "teste de segurança",
    }

def test_terminal_operation_checkpoint_persists_identity_across_runtime_rebuild(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    now = datetime.now(timezone.utc)
    runtime.lineage.put(OperationLineage("decision-001", "cycle-001", "req-001", external_id="ext-001", updated_at=now))
    runtime.operation_context.put("req-001", DecisionSnapshot(
        signal="COMPRA", analysis_score=80, confirmed=True, quality_score=80,
        quality_level="HIGH", actionable=True, decision="EXECUTAR",
        decision_reason="test", market_context=None, market_direction=None,
        market_score=None, operational_state_available=True, trades_today=0,
        consecutive_losses=0, symbol="EURUSD", timeframe="5m",
        decision_id="decision-001", cycle_id="cycle-001", request_id="req-001",
    ))
    assert runtime.checkpoint_operation("req-001", decision_id="decision-001", cycle_id="cycle-001") is True

    checkpoint = runtime.checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.last_cycle == 1
    assert checkpoint.last_request_id == "req-001"
    assert checkpoint.last_decision_id == "decision-001"
    assert checkpoint.last_cycle_id == "cycle-001"
    assert checkpoint.session_id == runtime.session_id
    runtime.execution_ledger.reserve("req-001")
    runtime.execution_ledger.mark_accepted("req-001")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord("req-001", ExecutionLifecycleState.ACCEPTED, now)
    )

    rebuilt = build_operational_runtime(tmp_path)
    assert rebuilt.recovery.assess().state.value == "SAFE_TO_RESUME"
    assert rebuilt.checkpoint_store.load().last_cycle == 1
    assert rebuilt.checkpoint_store.load().last_request_id == "req-001"
    assert rebuilt.session_id != runtime.session_id
    assert rebuilt.checkpoint_store.load().session_id == runtime.session_id


def test_checkpoint_cycles_increase_without_replaying_execution(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    runtime.checkpoint_operation("req-001")
    runtime.checkpoint_operation("req-002")

    checkpoint = runtime.checkpoint_store.load()
    assert checkpoint.last_cycle == 2
    assert checkpoint.last_request_id == "req-002"


def test_kill_switch_state_survives_runtime_rebuild(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    runtime.activate_kill_switch("bloqueio persistente")

    rebuilt = build_operational_runtime(tmp_path)

    assert rebuilt.kill_switch.state.enabled is True
    assert rebuilt.kill_switch.state.reason == "bloqueio persistente"
    assert rebuilt.gateway._kill_switch is rebuilt.kill_switch


def test_corrupt_persisted_safety_state_fails_closed(tmp_path):
    path = tmp_path / "operational-safety.json"
    path.write_text("{invalid", encoding="utf-8")

    runtime = build_operational_runtime(tmp_path)

    assert runtime.kill_switch.state.enabled is True
    assert "inválido" in (runtime.kill_switch.state.reason or "")
    assert runtime.gateway._kill_switch is runtime.kill_switch



def test_daily_journal_claim_market_decision_is_atomic_across_instances(tmp_path):
    from core.daily_operation_journal import DailyOperationJournal

    first = DailyOperationJournal(tmp_path / "daily.json")
    second = DailyOperationJournal(tmp_path / "daily.json")
    timestamp = "2026-09-29T01:45:00+00:00"

    assert first.claim_market_decision(
        decision_id="d1",
        symbol="EURUSD",
        timeframe="5m",
        market_timestamp=timestamp,
    ) is True
    assert second.claim_market_decision(
        decision_id="d2",
        symbol="EURUSD",
        timeframe="5m",
        market_timestamp=timestamp,
    ) is False
