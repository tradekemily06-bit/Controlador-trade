from types import SimpleNamespace
from pathlib import Path

from integration.ecosystem_service import EcosystemService


def _runtime(tmp_path: Path):
    checkpoint = SimpleNamespace(path=tmp_path / "runtime-checkpoint.json")
    health = SimpleNamespace(
        assess=lambda: SimpleNamespace(
            state=SimpleNamespace(value="HEALTHY"),
            ledger_entries=0,
            pending_executions=0,
            unknown_executions=0,
            recovery_state=SimpleNamespace(value="SAFE_TO_RESUME"),
            message="ok",
        )
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
    automation_lifecycle = SimpleNamespace(load=lambda: {})
    return SimpleNamespace(
        checkpoint_store=checkpoint,
        health=health,
        recovery=recovery,
        kill_switch=kill_switch,
        market_data=market_data,
        automation_lifecycle=automation_lifecycle,
    )


def _write_status(path: Path, observed_at: str, reason: str):
    path.write_text(
        '{"component":"controlador","state":"HEALTHY","reason":"'
        + reason
        + '","observed_at":"'
        + observed_at
        + '"}',
        encoding="utf-8",
    )


def test_supervisor_health_status_is_preserved_when_fresh(tmp_path):
    from datetime import datetime, timezone

    status_path = tmp_path / "controlador-supervisor-status.json"
    _write_status(status_path, datetime.now(timezone.utc).isoformat(), "ok")

    observability = EcosystemService(operational_runtime=_runtime(tmp_path)).operational_observability()

    assert observability["supervision"]["controller"]["state"] == "HEALTHY"


def test_supervisor_health_status_expires_when_stale(tmp_path):
    status_path = tmp_path / "controlador-supervisor-status.json"
    _write_status(status_path, "2000-01-01T00:00:00+00:00", "old")

    observability = EcosystemService(operational_runtime=_runtime(tmp_path)).operational_observability()

    assert observability["supervision"]["controller"]["state"] == "UNKNOWN"
    assert observability["supervision"]["controller"]["reason"] == "telemetria de supervisão expirada"
