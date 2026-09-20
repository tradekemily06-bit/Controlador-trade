import pytest
from pathlib import Path

from core.file_lock import exclusive_file_lock
from core.operation_memory import OperationMemory
from core.operation_memory_store import OperationMemoryStore
from core.operational_safety_store import OperationalSafetyStore
from core.demo_risk_state_store import DemoRiskStateStore
from core.operational_state import OperationalState
from execution.execution_ledger import ExecutionLedger
from storage.scoped_state_store import SQLiteScopedStateStore
from storage.sqlite_production_store import SQLiteProductionStore
from analysis.decision_store import DecisionStore


def _symlinked_parent(tmp_path: Path, name: str = "link") -> Path:
    target = tmp_path / "real-parent"
    target.mkdir()
    parent = tmp_path / name
    parent.symlink_to(target, target_is_directory=True)
    return parent


def test_file_lock_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    with pytest.raises(RuntimeError):
        with exclusive_file_lock(parent / "state.lock"):
            pass


def test_file_lock_rejects_symlinked_lock_file(tmp_path):
    target = tmp_path / "target.lock"
    target.write_text("")
    link = tmp_path / "state.lock"
    link.symlink_to(target)
    with pytest.raises(RuntimeError):
        with exclusive_file_lock(link):
            pass


def test_ledger_load_rejects_symlink_state(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}")
    state = tmp_path / "ledger.json"
    state.symlink_to(target)
    with pytest.raises(ValueError):
        ExecutionLedger(state)


def test_ledger_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    with pytest.raises(RuntimeError):
        ExecutionLedger(parent / "ledger.json")


def test_memory_load_rejects_symlink_state(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("[]")
    state = tmp_path / "memory.json"
    state.symlink_to(target)
    store = OperationMemoryStore(state)
    with pytest.raises(ValueError):
        store.load()


def test_memory_rejects_symlinked_parent_on_save(tmp_path):
    parent = _symlinked_parent(tmp_path)
    with pytest.raises(RuntimeError):
        OperationMemoryStore(parent / "memory.json").save(OperationMemory())


def test_safety_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    with pytest.raises(RuntimeError):
        OperationalSafetyStore(parent / "safety.json").set_kill_switch(enabled=True, reason="test")


def test_demo_risk_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    store = DemoRiskStateStore(parent / "risk.json")
    with pytest.raises(OSError):
        store.replace(OperationalState(trades_today=0, consecutive_losses=0), source="reconciliation")


def test_scoped_state_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    with pytest.raises(RuntimeError):
        SQLiteScopedStateStore(parent / "state.db")


def test_production_store_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    with pytest.raises(RuntimeError):
        SQLiteProductionStore(parent / "production.db")


def test_decision_store_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    with pytest.raises(RuntimeError):
        DecisionStore(str(parent / "decisions.db"))


from core.technical_incident_store import TechnicalIncidentStore
from datetime import datetime, timezone


def test_technical_incident_rejects_symlinked_parent(tmp_path):
    parent = _symlinked_parent(tmp_path)
    store = TechnicalIncidentStore(parent / "incident.json")
    with pytest.raises(RuntimeError):
        store.open("incident-1", "test", now=datetime.now(timezone.utc))


def test_technical_incident_refuses_stale_temp(tmp_path):
    state = tmp_path / "incident.json"
    (tmp_path / ".incident.json.tmp").write_text("stale")
    store = TechnicalIncidentStore(state)
    with pytest.raises(RuntimeError):
        store.open("incident-1", "test", now=datetime.now(timezone.utc))



def test_sqlite_paths_are_revalidated_after_initialization(tmp_path):
    from security_audit import SecurityAudit
    from analysis.decision_store import DecisionStore

    decision_path = tmp_path / "decision.db"
    decision_store = DecisionStore(str(decision_path))
    target = tmp_path / "decision-target.db"
    target.write_bytes(decision_path.read_bytes())
    decision_path.unlink()
    decision_path.symlink_to(target)
    with pytest.raises(RuntimeError):
        decision_store.load()

    audit_path = tmp_path / "audit.db"
    audit = SecurityAudit(database_path=str(audit_path), require_durable=True)
    audit_target = tmp_path / "audit-target.db"
    audit_target.write_bytes(audit_path.read_bytes())
    audit_path.unlink()
    audit_path.symlink_to(audit_target)
    with pytest.raises(RuntimeError):
        audit.record(request_id="r", method="GET", path="/", status=200, client_key="client")
