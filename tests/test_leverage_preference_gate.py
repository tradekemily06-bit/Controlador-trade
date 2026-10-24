from app import _mode_execution_block_reason


def test_leverage_mode_blocks_execution_until_risk_profile_is_validated():
    reason = _mode_execution_block_reason({"selected_mode": "DEMO", "leverage_enabled": True})
    assert "execução bloqueada" in reason
    assert "orçamento de risco" in reason


def test_leverage_mode_disabled_does_not_add_a_leverage_block():
    assert _mode_execution_block_reason({"selected_mode": "DEMO", "leverage_enabled": False}) == ""


def test_real_mode_remains_blocked_even_when_leverage_mode_is_disabled():
    reason = _mode_execution_block_reason({"selected_mode": "REAL", "leverage_enabled": False})
    assert "REAL permanece bloqueada" in reason
