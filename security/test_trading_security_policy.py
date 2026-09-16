from security.trading_security_policy import (
    BrokerSecurityPosture,
    SecurityReadiness,
    TradingSecurityPolicy,
)


def test_security_policy_fails_closed_when_critical_controls_are_missing():
    result = TradingSecurityPolicy().assess(BrokerSecurityPosture())
    assert result.readiness is SecurityReadiness.BLOCKED
    assert result.protected_operation_allowed is False
    assert result.execution_authorized is False
    assert "MFA não está habilitado" in result.blocking_reasons
    assert "permissão de saque/withdrawal da API está habilitada" not in result.blocking_reasons


def test_withdrawal_permission_is_always_a_blocking_security_failure():
    posture = BrokerSecurityPosture(
        mfa_enabled=True,
        phishing_resistant_mfa=True,
        api_withdrawal_enabled=True,
        active_permissions=frozenset({"READ", "TRADE", "WITHDRAWAL"}),
        broker_session_healthy=True,
        market_connection_healthy=True,
        protective_orders_supported=True,
        protective_orders_active=True,
        security_incident_clear=True,
        security_state_available=True,
    )
    result = TradingSecurityPolicy().assess(posture)
    assert result.readiness is SecurityReadiness.BLOCKED
    assert any("saque" in reason for reason in result.blocking_reasons)


def test_fully_hardened_posture_is_ready_but_never_grants_execution_authority():
    posture = BrokerSecurityPosture(
        mfa_enabled=True,
        phishing_resistant_mfa=True,
        api_withdrawal_enabled=False,
        broker_session_healthy=True,
        market_connection_healthy=True,
        protective_orders_supported=True,
        protective_orders_active=True,
        security_incident_clear=True,
        security_state_available=True,
        backup_connection_available=True,
        dedicated_runtime=True,
        vps_or_hardened_runtime=True,
    )
    result = TradingSecurityPolicy().assess(posture)
    assert result.readiness is SecurityReadiness.READY
    assert result.protected_operation_allowed is True
    assert result.execution_authorized is False


def test_network_loss_does_not_log_user_out_but_operation_can_be_blocked_elsewhere():
    policy = TradingSecurityPolicy.session_policy()
    assert policy.allow_multiple_devices is True
    assert policy.new_device_disconnects_existing is False
    assert policy.disconnect_requires_explicit_action is True
    assert policy.network_loss_logs_user_out is False
    assert policy.security_event_may_revoke_sessions is True
