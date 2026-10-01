from core.automation_lifecycle_store import AutomationLifecycleStore
from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleState


def test_automation_lifecycle_survives_restart(tmp_path):
    path = tmp_path / "automation-lifecycle.json"
    store = AutomationLifecycleStore(path)
    lifecycle = AutomationLifecycle("cycle-1", AutomationLifecycleState.DISPATCHED)

    store.save(lifecycle)

    restarted = AutomationLifecycleStore(path)
    assert restarted.load()["cycle-1"] == lifecycle


def test_invalid_persisted_lifecycle_is_ignored(tmp_path):
    path = tmp_path / "automation-lifecycle.json"
    path.write_text(
        '{"version":1,"cycles":{"good":"COMPLETED","bad":"NOT_A_STATE","empty":""}}',
        encoding="utf-8",
    )

    loaded = AutomationLifecycleStore(path).load()

    assert loaded["good"].state is AutomationLifecycleState.COMPLETED
    assert "bad" not in loaded
    assert "empty" not in loaded
