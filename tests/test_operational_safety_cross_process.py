from datetime import datetime, timezone

from core.kill_switch import KillSwitch
from core.operational_safety_store import OperationalSafetyStore
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


def request(request_id="cross-process-kill"):
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id=request_id,
    )


def test_gateway_refreshes_kill_switch_written_by_another_runtime(tmp_path):
    safety_path = tmp_path / "operational-safety.json"
    store_a = OperationalSafetyStore(safety_path)
    store_b = OperationalSafetyStore(safety_path)

    kill_a = KillSwitch()
    audit_a, _ = store_a.load()
    kill_a.activate("emergência global")
    store_a.save(audit_a, kill_a)

    executor = PaperExecutor()
    local_kill_b = KillSwitch()
    gateway_b = ExecutionGateway(executor, local_kill_b, safety_store=store_b)

    result = gateway_b.execute("cross-process-kill", request())

    assert result.status is GatewayStatus.BLOCKED
    assert "emergência global" in result.message
    assert executor.executions() == ()
    assert local_kill_b.state.enabled is True


def test_gateway_fails_closed_when_authoritative_safety_state_is_corrupt(tmp_path):
    safety_path = tmp_path / "operational-safety.json"
    safety_path.write_text("{corrupt", encoding="utf-8")

    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), safety_store=OperationalSafetyStore(safety_path))

    result = gateway.execute("corrupt-safety", request())

    assert result.status is GatewayStatus.BLOCKED
    assert "estado de segurança indisponível" in result.message
    assert executor.executions() == ()


def test_execution_audit_updates_from_two_process_views_are_merged(tmp_path):
    path = tmp_path / "operational-safety.json"
    first = OperationalSafetyStore(path)
    second = OperationalSafetyStore(path)
    first.save_execution_audit(({
        "request_id": "req-a",
        "state": "PENDING",
        "timestamp": datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc).isoformat(),
        "message": "a",
    },))
    second.save_execution_audit(({
        "request_id": "req-b",
        "state": "PENDING",
        "timestamp": datetime(2026, 9, 14, 20, 0, 1, tzinfo=timezone.utc).isoformat(),
        "message": "b",
    },))

    events = second.load_execution_audit()

    assert [event["request_id"] for event in events] == ["req-a", "req-b"]
