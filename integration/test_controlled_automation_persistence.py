from core.automation_lifecycle_store import AutomationLifecycleStore
from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleState
from integration.controlled_automation_service import ControlledAutomationService


def test_controlled_automation_service_restores_lifecycle_after_restart(tmp_path):
    store = AutomationLifecycleStore(tmp_path / "automation-lifecycle.json")
    store.save(AutomationLifecycle("cycle-restart", AutomationLifecycleState.DISPATCHED))

    restarted = ControlledAutomationService(lifecycle_store=store)

    assert restarted.lifecycle("cycle-restart").state is AutomationLifecycleState.DISPATCHED
