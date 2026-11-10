from datetime import datetime, timezone

from integration.ecosystem_service import EcosystemService
from core.operational_runtime import build_operational_runtime
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
from core.models import Signal
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def test_shared_runtime_starts_fail_closed_and_exposes_authoritative_state(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)

    snapshot = service.operational_observability()

    assert runtime.gateway._kill_switch is runtime.kill_switch
    assert runtime.gateway._ledger is runtime.execution_ledger
    assert runtime.gateway._lifecycle is runtime.execution_lifecycle
    assert runtime.gateway._recovery is runtime.recovery
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


def test_kill_switch_activation_is_persisted_and_restored_fail_closed(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    runtime.operational_recorder.activate_kill_switch("parada de emergência")

    restored = build_operational_runtime(tmp_path)
    snapshot = EcosystemService(operational_runtime=restored).operational_observability()

    assert restored.kill_switch.state.enabled is True
    assert restored.kill_switch.state.reason == "parada de emergência"
    assert snapshot["kill_switch"] == {
        "state": "ACTIVE",
        "enabled": True,
        "reason": "parada de emergência",
    }
    assert snapshot["execution"]["state"] == "BLOCKED"



def test_kill_switch_persists_active_intent_before_in_memory_transition(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    observed = {}

    class ObservingSafetyStore:
        def save(self, audit, persisted_kill_switch):
            observed["persisted_enabled"] = persisted_kill_switch.state.enabled
            observed["persisted_reason"] = persisted_kill_switch.state.reason
            observed["runtime_enabled_during_persist"] = runtime.kill_switch.state.enabled

    runtime.operational_recorder.safety_store = ObservingSafetyStore()
    state = runtime.operational_recorder.activate_kill_switch("falha crítica")

    assert observed == {
        "persisted_enabled": True,
        "persisted_reason": "falha crítica",
        "runtime_enabled_during_persist": False,
    }
    assert state.enabled is True
    assert runtime.kill_switch.state.enabled is True


def test_kill_switch_remains_active_in_process_when_persistence_fails(tmp_path):
    runtime = build_operational_runtime(tmp_path)

    class BrokenSafetyStore:
        def save(self, _audit, _persisted_kill_switch):
            raise OSError("disco indisponível")

    runtime.operational_recorder.safety_store = BrokenSafetyStore()
    try:
        runtime.operational_recorder.activate_kill_switch("falha crítica")
    except OSError:
        pass
    else:
        raise AssertionError("a falha de persistência deveria ser propagada")

    assert runtime.kill_switch.state.enabled is True
    assert runtime.kill_switch.state.reason == "falha crítica"
    assert runtime.gateway._kill_switch is runtime.kill_switch


def test_kill_switch_does_not_report_success_without_persistent_storage(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    runtime.operational_recorder.safety_store = None

    try:
        runtime.operational_recorder.activate_kill_switch("persistência indisponível")
    except RuntimeError as exc:
        assert "armazenamento persistente" in str(exc)
    else:
        raise AssertionError("ativação sem persistência não pode ser confirmada")

    assert runtime.kill_switch.state.enabled is True
    assert runtime.kill_switch.state.reason == "persistência indisponível"
    assert runtime.gateway._kill_switch is runtime.kill_switch



def _valid_demo_request():
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_gateway_blocks_new_dispatch_while_old_request_is_pending(tmp_path):
    executor = PaperExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord("old-pending", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc))
    )

    result = runtime.gateway.execute("new-request", _valid_demo_request())

    assert result.status.value == "BLOCKED"
    assert "reconciliação operacional necessária" in result.message
    assert executor.executions() == ()


def test_gateway_blocks_new_dispatch_while_old_request_is_unknown(tmp_path):
    executor = PaperExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord("old-unknown", ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc))
    )

    result = runtime.gateway.execute("new-request", _valid_demo_request())

    assert result.status.value == "BLOCKED"
    assert executor.executions() == ()


def test_gateway_blocks_new_dispatch_when_recovery_persistence_is_invalid(tmp_path):
    executor = PaperExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    (tmp_path / "runtime-checkpoint.json").write_text("{invalid", encoding="utf-8")

    result = runtime.gateway.execute("new-request", _valid_demo_request())

    assert result.status.value == "BLOCKED"
    assert "INVALID" in result.message
    assert executor.executions() == ()


def test_gateway_blocks_new_dispatch_when_ledger_and_lifecycle_diverge(tmp_path):
    executor = PaperExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    runtime.execution_ledger.reserve("old-divergent")
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord("old-divergent", ExecutionLifecycleState.REJECTED, datetime.now(timezone.utc))
    )

    result = runtime.gateway.execute("new-request", _valid_demo_request())

    assert result.status.value == "BLOCKED"
    assert executor.executions() == ()
