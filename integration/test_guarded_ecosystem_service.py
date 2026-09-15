from pathlib import Path

from core.operational_runtime import build_operational_runtime
from integration.guarded_ecosystem_service import GuardedEcosystemService


def test_guarded_service_blocks_analysis_when_kill_switch_is_active(tmp_path: Path):
    runtime = build_operational_runtime(tmp_path)
    runtime.kill_switch.activate("teste de bloqueio global")
    service = GuardedEcosystemService(operational_runtime=runtime)

    record = service.analyze({"score": 95, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "M5"}, persist=False)

    assert record.signal.value == "AGUARDAR"
    assert "bloqueada" in record.reason.lower()
    assert service.risk_status()["allowed"] is False
    assert service.operational_barrier_status()["operationally_allowed"] is False


def test_guarded_service_reports_missing_runtime_as_blocked():
    service = GuardedEcosystemService()

    status = service.operational_barrier_status()

    assert status["status"] == "BLOCKED"
    assert status["operationally_allowed"] is False
