from datetime import datetime, timedelta, timezone

from core.ecosystem_maintenance import MaintenanceManager, MaintenanceStatus, MaintenanceWindow
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest


class Executor:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        raise AssertionError("executor must not be reached during active maintenance")


def test_final_maintenance_barrier_ignores_stale_event_timestamp():
    maintenance = MaintenanceManager()
    now = datetime.now(timezone.utc)
    maintenance._current = MaintenanceWindow(
        maintenance_id="live-maintenance", title="Maintenance", message="live maintenance",
        starts_at=now - timedelta(minutes=1), ends_at=now + timedelta(minutes=1),
        status=MaintenanceStatus.ACTIVE,
    )
    executor = Executor()
    gateway = ExecutionGateway(executor, KillSwitch(), maintenance=maintenance)
    request = ExecutionRequest("EURUSD", Signal.COMPRA, 1.0, 60, ExecutionMode.DEMO)

    result = gateway.execute(
        "stale-maintenance",
        request,
        timestamp=now - timedelta(days=1),
    )

    assert result.status is GatewayStatus.BLOCKED
    assert executor.calls == 0
