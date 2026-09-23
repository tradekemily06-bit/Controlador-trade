from core.safe_automation import AutomationClass, SafeAutomationAction, SafeAutomationPolicy, UserAction, classify_maintenance


def test_bookkeeping_is_safe_automation():
    assert SafeAutomationPolicy.classify(SafeAutomationAction.JOURNAL_OPERATION.value) is AutomationClass.SAFE
    assert classify_maintenance(SafeAutomationAction.REFRESH_DERIVED_STATE.value).allowed_automatically is True


def test_money_movement_and_security_changes_stay_manual():
    for action in (
        UserAction.EXECUTE_OPERATION.value,
        UserAction.AUTHORIZE_REAL.value,
        UserAction.RESOLVE_UNKNOWN_EXECUTION.value,
        UserAction.DISABLE_KILL_SWITCH.value,
        UserAction.CHANGE_SECURITY_CONFIGURATION.value,
    ):
        decision = classify_maintenance(action)
        assert decision.classification is AutomationClass.REQUIRES_USER
        assert decision.allowed_automatically is False


def test_unknown_automation_is_not_silently_allowed():
    decision = classify_maintenance("DELETE_BROKER_STATE")
    assert decision.classification is AutomationClass.FORBIDDEN
    assert decision.allowed_automatically is False
