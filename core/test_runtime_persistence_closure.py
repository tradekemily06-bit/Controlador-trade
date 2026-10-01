from datetime import datetime, timezone

from core.operational_runtime import build_operational_runtime


def test_kill_switch_survives_runtime_restart(tmp_path):
    first = build_operational_runtime(tmp_path)
    first.activate_kill_switch("teste persistente")

    second = build_operational_runtime(tmp_path)

    assert second.kill_switch.state.enabled is True
    assert second.kill_switch.state.reason == "teste persistente"
    assert second.gateway._kill_switch is second.kill_switch


def test_kill_switch_clear_survives_runtime_restart(tmp_path):
    first = build_operational_runtime(tmp_path)
    first.activate_kill_switch("bloqueio")
    first.deactivate_kill_switch()

    second = build_operational_runtime(tmp_path)

    assert second.kill_switch.state.enabled is False
    assert second.kill_switch.state.reason is None
