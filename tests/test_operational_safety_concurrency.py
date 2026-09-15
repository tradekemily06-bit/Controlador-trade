from core.decision_audit import DecisionAudit
from core.kill_switch import KillSwitch
from core.operational_safety_store import OperationalSafetyStore


def test_stale_audit_save_cannot_clear_persisted_kill_switch(tmp_path):
    path = tmp_path / "safety.json"
    store_a = OperationalSafetyStore(path)
    store_b = OperationalSafetyStore(path)
    audit_a = DecisionAudit()
    audit_b = DecisionAudit()
    switch_a = KillSwitch()
    switch_b = KillSwitch()

    store_a.set_kill_switch(enabled=True, reason="emergency")
    store_b.save(audit_b, switch_b)

    _, restored = store_a.load()
    assert restored.state.enabled is True
    assert restored.state.reason == "emergency"


def test_explicit_kill_switch_transition_can_deactivate_under_lock(tmp_path):
    store = OperationalSafetyStore(tmp_path / "safety.json")
    store.set_kill_switch(enabled=True, reason="test")
    state = store.set_kill_switch(enabled=False)
    assert state.enabled is False
    assert state.reason is None
    _, restored = store.load()
    assert restored.state.enabled is False
