from security.saas_production_baseline import SaaSProductionSecurityState


def test_default_production_security_state_is_blocked() -> None:
    state = SaaSProductionSecurityState()
    assert state.ready is False
    assert state.authorize_protected_operation() is False
    assert state.status()["status"] == "BLOCKED"
    assert state.status()["real_execution"] == "DISABLED"


def test_production_security_state_requires_every_prerequisite() -> None:
    values = dict(
        trusted_identity=True,
        tenant_isolated_durable_storage=True,
        secure_transport=True,
        secret_management=True,
        durable_audit=True,
        centralized_rate_limiting=True,
    )
    state = SaaSProductionSecurityState(**values)
    assert state.ready is True
    assert state.authorize_protected_operation() is True
    assert state.status()["status"] == "READY"


def test_real_execution_can_never_make_the_gate_ready() -> None:
    state = SaaSProductionSecurityState(
        trusted_identity=True,
        tenant_isolated_durable_storage=True,
        secure_transport=True,
        secret_management=True,
        durable_audit=True,
        centralized_rate_limiting=True,
        real_execution_enabled=True,
    )
    assert state.ready is False
    assert state.authorize_protected_operation() is False
    assert state.status()["real_execution"] == "ENABLED"
