from core.automation_risk_policy import AutomationRiskPolicy


def test_missing_environment_is_unconfigured(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_RISK_MAX_ORDER_VOLUME", raising=False)
    monkeypatch.delenv("CONTROLADOR_RISK_MAX_TOTAL_VOLUME", raising=False)
    policy = AutomationRiskPolicy.from_environment()
    assert policy.configured is False
    assert policy.limits() is None


def test_environment_is_explicit_policy(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_ORDER_VOLUME", "0.10")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_TOTAL_VOLUME", "0.30")
    policy = AutomationRiskPolicy.from_environment()
    assert policy.configured is True
    limits = policy.limits()
    assert limits.max_order_amount == 0.10
    assert limits.max_total_exposure == 0.30


def test_invalid_environment_does_not_fallback_to_a_default(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_ORDER_VOLUME", "not-a-number")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_TOTAL_VOLUME", "-1")
    policy = AutomationRiskPolicy.from_environment()
    assert policy.configured is False
    assert policy.limits() is None
