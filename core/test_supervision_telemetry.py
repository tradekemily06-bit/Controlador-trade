from types import SimpleNamespace
from pathlib import Path

from integration.ecosystem_service import EcosystemService


def _runtime(tmp_path: Path):
    checkpoint = SimpleNamespace(path=tmp_path / "runtime-checkpoint.json")
    health = SimpleNamespace(
        assess=lambda: SimpleNamespace(state=SimpleNamespace(value="HEALTHY"), ledger_entries=0, pending_executions=0, unknown_executions=0, recovery_state=SimpleNamespace(value="SAFE_TO_RESUME"), message="ok")
    )
    recovery = SimpleNamespace(
        assess=lambda: SimpleNamespace(
            can_resume=True,
            state=SimpleNamespace(value="SAFE_TO_RESUME"),
            pending_request_ids=(),
            unknown_request_ids=(),
            message="ok",
        )
    )
    kill_switch = SimpleNamespace(state=SimpleNamespace(enabled=False, reason=None))
    market_data = SimpleNamespace(status=lambda: {"health": "HEALTHY"})
    automation_lifecycle = SimpleNamespace()
    return SimpleNamespace(
        checkpoint_store=checkpoint,
        health=health,
        recovery=recovery,
        kill_switch=kill_switch,
        market_data=market_data,
        automation_lifecycle=automation_lifecycle,
    )


def test_supervisor_health_status_is_preserved_when_fresh(tmp_path):
    runtime = _runtime(tmp_path)
    status_path = tmp_path / "controlador-supervisor-status.json"
    from datetime import datetime, timezone
    status_path.write_text(
        '{"component":"controlador","state":"HEALTHY","reason":"ok","observed_at":"'
        + datetime.now(timezone.utc).isoformat()
        + '"}',
        encoding="utf-8",
    )

    observability = EcosystemService(operational_runtime=runtime).operational_observability()

    assert observability["supervision"]["controller"]["state"] == "HEALTHY"


def test_supervisor_health_status_expires_when_stale(tmp_path):
    runtime = _runtime(tmp_path)
    status_path = tmp_path / "controlador-supervisor-status.json"
    status_path.write_text(
        '{"component":"controlador","state":"HEALTHY","reason":"old","observed_at":"2000-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )

    observability = EcosystemService(operational_runtime=runtime).operational_observability()

    assert observability["supervision"]["controller"]["state"] == "UNKNOWN"
    assert observability["supervision"]["controller"]["reason"] == "telemetria de supervisão expirada"
