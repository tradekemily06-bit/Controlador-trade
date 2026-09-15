import pytest

from core.risk_manager import RiskManager


def test_permite_dentro_do_limite():
    manager = RiskManager(daily_loss_limit=100)
    assert manager.can_execute(daily_result=-50, operations_count=0, consecutive_losses=0)


def test_bloqueia_limite_diario():
    manager = RiskManager(daily_loss_limit=100)
    assert not manager.can_execute(daily_result=-100, operations_count=0, consecutive_losses=0)


def test_bloqueia_perda_acima_do_limite():
    manager = RiskManager(daily_loss_limit=100)
    assert not manager.can_execute(daily_result=-101, operations_count=0, consecutive_losses=0)


def test_limite_operacoes():
    manager = RiskManager(max_operations=5)
    assert manager.can_execute(daily_result=0, operations_count=4, consecutive_losses=0)
    assert not manager.can_execute(daily_result=0, operations_count=5, consecutive_losses=0)


def test_limite_perdas_consecutivas():
    manager = RiskManager(max_consecutive_losses=3)
    assert manager.can_execute(daily_result=0, operations_count=0, consecutive_losses=2)
    assert not manager.can_execute(daily_result=0, operations_count=0, consecutive_losses=3)


def test_can_execute_rejeita_estado_legacy_parcial():
    manager = RiskManager(daily_loss_limit=100)
    assert manager.can_execute(daily_result=-50) is False
    assert manager.can_execute(operations_count=0) is False
    assert manager.can_execute(consecutive_losses=0) is False


def test_can_execute_sem_estado_e_fail_closed():
    assert RiskManager().can_execute() is False


def test_calculo_risco():
    assert RiskManager.calculate_position_risk(
        account_balance=1000,
        risk_percent=1,
    ) == 10


def test_risco_zero():
    assert RiskManager.calculate_position_risk(
        account_balance=1000,
        risk_percent=0,
    ) == 0


def test_rejeita_percentual_invalido():
    with pytest.raises(ValueError):
        RiskManager.calculate_position_risk(
            account_balance=1000,
            risk_percent=101,
        )


def test_rejeita_saldo_negativo():
    with pytest.raises(ValueError):
        RiskManager.calculate_position_risk(
            account_balance=-100,
            risk_percent=1,
        )


def test_rejeita_configuracao_negativa():
    with pytest.raises(ValueError):
        RiskManager(max_operations=-1)


def test_sem_limite_de_operacoes_quando_zero():
    manager = RiskManager(max_operations=0)
    assert manager.can_execute(daily_result=0, operations_count=1000, consecutive_losses=0)
