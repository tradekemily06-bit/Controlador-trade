from core.broker_security_policy import BrokerPermission, BrokerSecurityPolicy, MfaMethod


def test_withdrawal_permission_is_always_rejected():
    assessment = BrokerSecurityPolicy().assess_api_permissions({BrokerPermission.READ, BrokerPermission.TRADE, BrokerPermission.WITHDRAWAL})
    assert assessment.allowed is False
    assert assessment.execution_authorized is False


def test_read_and_trade_without_withdrawal_passes_policy_but_not_authorization():
    assessment = BrokerSecurityPolicy().assess_api_permissions({BrokerPermission.READ, BrokerPermission.TRADE})
    assert assessment.allowed is True
    assert assessment.execution_authorized is False


def test_production_requires_strong_mfa():
    policy = BrokerSecurityPolicy()
    assert policy.assess_account_mfa(MfaMethod.AUTHENTICATOR, production=True).allowed
    assert policy.assess_account_mfa(MfaMethod.SECURITY_KEY, production=True).allowed
    assert not policy.assess_account_mfa(MfaMethod.SMS, production=True).allowed
    assert not policy.assess_account_mfa(None, production=True).allowed


def test_production_requires_broker_side_protection():
    policy = BrokerSecurityPolicy()
    assert not policy.assess_protection_orders(production=True, broker_side_protection_confirmed=False).allowed
    assert policy.assess_protection_orders(production=True, broker_side_protection_confirmed=True).allowed
    assert policy.assess_protection_orders(production=False, broker_side_protection_confirmed=False).allowed


def test_ip_allowlist_is_opt_in_and_fail_closed_when_enabled():
    policy = BrokerSecurityPolicy()
    assert policy.assess_ip_policy(source_ip="1.2.3.4", allowed_ips=None, enforce=False).allowed
    assert not policy.assess_ip_policy(source_ip="1.2.3.4", allowed_ips={"5.6.7.8"}, enforce=True).allowed
    assert policy.assess_ip_policy(source_ip="1.2.3.4", allowed_ips={"1.2.3.4"}, enforce=True).allowed
