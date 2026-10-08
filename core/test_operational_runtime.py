from datetime import datetime, timezone

from integration.ecosystem_service import EcosystemService
from core.operational_runtime import build_operational_runtime
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


def test_shared_runtime_uses_persistent_operational_recorder(tmp_path):
    runtime = build_operational_runtime(tmp_path)

    assert runtime.operational_recorder is runtime.gateway._recorder
    assert runtime.operational_recorder.store.path == tmp_path / "operation-memory.json"
    assert runtime.operational_recorder.safety_store.path == tmp_path / "operational-safety.json"

    restored = runtime.operational_recorder.__class__.from_path(
        tmp_path / "operation-memory.json",
        kill_switch=runtime.kill_switch,
        safety_path=tmp_path / "operational-safety.json",
    )
    assert restored.memory.records() == ()



def test_supervisor_status_accepts_utf8_bom(tmp_path):
    import json

    runtime = build_operational_runtime(tmp_path)
    for name, component in (("controlador-supervisor-status.json", "controlador"), ("mt5-supervisor-status.json", "mt5")):
        (tmp_path / name).write_text(
            json.dumps({"component": component, "state": "HEALTHY", "reason": "teste"}),
            encoding="utf-8-sig",
        )

    snapshot = EcosystemService(operational_runtime=runtime).operational_observability()

    assert snapshot["supervision"]["controller"]["state"] == "HEALTHY"
    assert snapshot["supervision"]["mt5"]["state"] == "HEALTHY"
