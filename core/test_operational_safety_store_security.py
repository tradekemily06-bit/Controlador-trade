import pytest
from core.operational_safety_store import OperationalSafetyStore

def test_safety_store_rejects_symlink_and_stale_temp(tmp_path):
    target=tmp_path/"target.json"; target.write_text("{}")
    state=tmp_path/"safety.json"; state.symlink_to(target)
    store=OperationalSafetyStore(state)
    with pytest.raises(OSError): store.set_kill_switch(enabled=True, reason="test")

def test_safety_store_refuses_stale_temp(tmp_path):
    state=tmp_path/"safety.json"; (tmp_path/"safety.json.tmp").write_text("x")
    with pytest.raises(RuntimeError): OperationalSafetyStore(state).set_kill_switch(enabled=True, reason="test")
