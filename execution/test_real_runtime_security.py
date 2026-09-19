from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.operational_safety_store import OperationalSafetyStore
from core.p112_real_execution_contract import RealExecutionAuthorization
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.real_runtime import build_real_execution_runtime


def test_real_runtime_requires_persisted_safety_state(tmp_path: Path):
    registry = BrokerRegistry()
    auth = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    with pytest.raises(RuntimeError, match="estado de segurança REAL ausente"):
        build_real_execution_runtime(tmp_path, registry, auth)


def test_real_runtime_uses_persisted_kill_switch_instance(tmp_path: Path):
    root = tmp_path
    store = OperationalSafetyStore(root / "safety.json")
    audit_path = root / "operations.json"
    from core.decision_audit import DecisionAudit
    store.save(DecisionAudit(), KillSwitch())
    kill_switch = KillSwitch()
    kill_switch.activate("emergência")
    store.save_kill_switch(kill_switch)

    registry = BrokerRegistry()
    auth = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    runtime = build_real_execution_runtime(root, registry, auth)

    assert runtime.kill_switch is runtime.gateway._kill_switch
    assert runtime.kill_switch.state.enabled is True
    assert runtime.gateway._ledger is runtime.ledger


def test_ledger_rejects_lock_symlink(tmp_path: Path):
    path = tmp_path / "ledger.json"
    lock = tmp_path / ".ledger.json.lock"
    target = tmp_path / "attacker-target"
    target.write_text("x", encoding="utf-8")
    try:
        lock.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink não suportado neste ambiente")

    ledger = ExecutionLedger(path)
    with pytest.raises(OSError):
        ledger.reserve("req")
    assert target.read_text(encoding="utf-8") == "x"
