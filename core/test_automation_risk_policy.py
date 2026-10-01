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


def test_environment_reads_explicit_max_loss_per_operation(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_LOSS_PER_OPERATION", "12.5")
    policy = AutomationRiskPolicy.from_environment()
    assert policy.max_loss_per_operation == 12.5


def test_missing_max_loss_per_operation_stays_unknown(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_RISK_MAX_LOSS_PER_OPERATION", raising=False)
    assert AutomationRiskPolicy.from_environment().max_loss_per_operation is None


def test_p40_runtime_blocks_when_operation_loss_is_missing(monkeypatch):
    from types import SimpleNamespace
    from core.p40_risk_budget import BudgetDecision
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.delenv("CONTROLADOR_RISK_MAX_LOSS_PER_OPERATION", raising=False)
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_DAILY_LOSS", "100")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_OPERATIONS", "10")
    service = SimpleNamespace(automation_risk_policy=AutomationRiskPolicy.from_environment())
    result = ConfiguredEcosystemService._build_mt5_automation_risk_budget(
        service,
        SimpleNamespace(realized_pnl=0.0, realized_loss_today=0.0, trades_today=0),
        SimpleNamespace(amount=0.01),
        SimpleNamespace(),
    )
    assert result.decision is BudgetDecision.BLOCKED
    assert "perda máxima por operação" in result.reason


def test_p40_runtime_uses_configured_operation_loss(monkeypatch):
    from types import SimpleNamespace
    from core.p40_risk_budget import BudgetDecision
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setenv("CONTROLADOR_RISK_MAX_LOSS_PER_OPERATION", "12.5")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_DAILY_LOSS", "100")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_OPERATIONS", "10")
    service = SimpleNamespace(automation_risk_policy=AutomationRiskPolicy.from_environment())
    result = ConfiguredEcosystemService._build_mt5_automation_risk_budget(
        service,
        SimpleNamespace(realized_pnl=0.0, realized_loss_today=0.0, trades_today=2),
        SimpleNamespace(amount=0.01),
        SimpleNamespace(),
    )
    assert result.decision is BudgetDecision.APPROVED
    assert result.projected_loss == 12.5
    assert result.projected_operations == 3


def test_p40_runtime_requires_explicit_daily_loss_and_operation_limits(monkeypatch):
    from types import SimpleNamespace
    from core.p40_risk_budget import BudgetDecision
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setenv("CONTROLADOR_RISK_MAX_LOSS_PER_OPERATION", "12.5")
    monkeypatch.delenv("CONTROLADOR_RISK_MAX_DAILY_LOSS", raising=False)
    monkeypatch.delenv("CONTROLADOR_RISK_MAX_OPERATIONS", raising=False)
    service = SimpleNamespace(automation_risk_policy=AutomationRiskPolicy.from_environment())
    result = ConfiguredEcosystemService._build_mt5_automation_risk_budget(
        service,
        SimpleNamespace(realized_pnl=0.0, trades_today=0),
        SimpleNamespace(amount=0.01),
        SimpleNamespace(),
    )
    assert result.decision is BudgetDecision.BLOCKED
    assert "orçamento P40" in result.reason


def test_p40_runtime_reads_explicit_daily_loss_and_operation_limits(monkeypatch):
    from types import SimpleNamespace
    from core.p40_risk_budget import BudgetDecision
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setenv("CONTROLADOR_RISK_MAX_LOSS_PER_OPERATION", "12.5")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_DAILY_LOSS", "100")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_OPERATIONS", "10")
    service = SimpleNamespace(automation_risk_policy=AutomationRiskPolicy.from_environment())
    result = ConfiguredEcosystemService._build_mt5_automation_risk_budget(
        service,
        SimpleNamespace(realized_pnl=0.0, trades_today=2),
        SimpleNamespace(amount=0.01),
        SimpleNamespace(),
    )
    assert result.decision is BudgetDecision.APPROVED
    assert result.projected_loss == 12.5
    assert result.projected_operations == 3


def test_p40_uses_sum_of_realized_losses_not_net_pnl(monkeypatch):
    from types import SimpleNamespace
    from core.p40_risk_budget import BudgetDecision
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setenv("CONTROLADOR_RISK_MAX_LOSS_PER_OPERATION", "12.5")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_DAILY_LOSS", "20")
    monkeypatch.setenv("CONTROLADOR_RISK_MAX_OPERATIONS", "10")
    service = SimpleNamespace(automation_risk_policy=AutomationRiskPolicy.from_environment())
    result = ConfiguredEcosystemService._build_mt5_automation_risk_budget(
        service,
        SimpleNamespace(realized_pnl=5.0, realized_loss_today=18.0, trades_today=2),
        SimpleNamespace(amount=0.01),
        SimpleNamespace(),
    )
    assert result.decision is BudgetDecision.BLOCKED
    assert result.projected_loss == 30.5
