from analysis.decision_store import DecisionStore
from integration.ecosystem_service import EcosystemService


def test_system_status_reports_in_memory_mode_by_default(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_DECISION_DB", raising=False)
    service = EcosystemService(decision_store=DecisionStore())

    status = service.system_status()

    assert status["memory"] == "ONLINE"
    assert status["memory_persistence"] == "IN_MEMORY"
    assert status["real"] == "DESABILITADO"


def test_system_status_reports_sqlite_mode_without_exposing_path(tmp_path):
    service = EcosystemService(decision_store=DecisionStore(str(tmp_path / "decisions.sqlite3")))

    status = service.system_status()

    assert status["memory_persistence"] == "SQLITE"
    assert str(tmp_path) not in str(status)
    assert "decision" not in status["memory_persistence"].lower()
