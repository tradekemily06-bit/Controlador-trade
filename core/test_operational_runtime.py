import pytest
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


def test_public_saas_multi_instance_runtime_fails_before_local_state_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    monkeypatch.setenv("CONTROLADOR_MULTI_INSTANCE", "true")

    with pytest.raises(RuntimeError, match="shared authoritative operational state provider"):
        build_operational_runtime(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_public_saas_single_instance_runtime_remains_supported(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    monkeypatch.delenv("CONTROLADOR_MULTI_INSTANCE", raising=False)

    runtime = build_operational_runtime(tmp_path)

    assert runtime.gateway._ledger is runtime.execution_ledger
    assert (tmp_path / "operational-safety.json").exists()


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


def test_execution_barrier_excludes_recovery_derived_checks(tmp_path):
    from core.operational_barrier_factory import build_global_operational_barrier

    runtime = build_operational_runtime(tmp_path)
    barrier = build_global_operational_barrier(runtime, include_recovery=False)

    names = {component.name for component in barrier._components}
    assert "execution-recovery" not in names
    assert "runtime-health" not in names
    assert "kill-switch" in names
    assert "operational-safety-store" in names
