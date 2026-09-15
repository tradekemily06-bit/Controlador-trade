from datetime import datetime, timezone

from core.ecosystem_incidents import EcosystemIncidentManager
from core.technical_incident_store import TechnicalIncidentStore
from core.kill_switch import KillSwitch
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


def request():
    return ExecutionRequest(symbol="BTCUSD", signal=Signal.COMPRA, amount=10.0, duration_seconds=60, mode=ExecutionMode.DEMO)


def test_incident_store_is_shared_across_runtime_workers(tmp_path):
    path = tmp_path / "technical-incident.json"
    first = EcosystemIncidentManager(store=TechnicalIncidentStore(path))
    second = EcosystemIncidentManager(store=TechnicalIncidentStore(path))

    first.open_incident(title="Falha técnica", message="dados indisponíveis", now=datetime(2026, 9, 15, tzinfo=timezone.utc))

    assert second.execution_blocked()
    assert second.status()["execution_blocked"] is True


def test_gateway_blocks_when_shared_incident_is_active(tmp_path):
    store = TechnicalIncidentStore(tmp_path / "technical-incident.json")
    manager = EcosystemIncidentManager(store=store)
    manager.open_incident(title="Falha técnica", message="executor indisponível")
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), incident_manager=manager)

    result = gateway.execute("incident-req", request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()


def test_corrupt_incident_state_blocks_execution(tmp_path):
    path = tmp_path / "technical-incident.json"
    path.write_text('{"status":"CORRUPT"}', encoding="utf-8")
    manager = EcosystemIncidentManager(store=TechnicalIncidentStore(path))
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), incident_manager=manager)

    result = gateway.execute("corrupt-incident", request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()
