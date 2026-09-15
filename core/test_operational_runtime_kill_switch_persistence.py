from pathlib import Path

from core.operational_runtime import build_operational_runtime
from core.operational_safety_store import OperationalSafetyStore


def test_kill_switch_survives_runtime_restart(tmp_path: Path):
    first = build_operational_runtime(tmp_path)
    first.kill_switch.activate("manual safety stop")
    assert first.kill_switch.allows_execution() is False

    restarted = build_operational_runtime(tmp_path)
    assert restarted.kill_switch.allows_execution() is False
    assert restarted.kill_switch.state.reason == "manual safety stop"


def test_corrupt_safety_state_fails_closed_and_is_repaired(tmp_path: Path):
    path = tmp_path / "operational-safety.json"
    path.write_text("not-json", encoding="utf-8")

    runtime = build_operational_runtime(tmp_path)
    assert runtime.kill_switch.allows_execution() is False
    assert "estado de segurança indisponível" in (runtime.kill_switch.state.reason or "")

    repaired = OperationalSafetyStore(path).load()
    _, persisted_switch = repaired
    assert persisted_switch.allows_execution() is False
    assert "estado de segurança indisponível" in (persisted_switch.state.reason or "")


def test_safety_store_recovery_does_not_read_corrupt_payload(tmp_path: Path):
    path = tmp_path / "operational-safety.json"
    path.write_text("{corrupt", encoding="utf-8")

    store = OperationalSafetyStore(path)
    store.replace_with_fail_closed_state("recovery required")

    _, kill_switch = store.load()
    assert kill_switch.allows_execution() is False
    assert kill_switch.state.reason == "recovery required"
