from core.market_context_reasoning import reason_market_context
from integration.ecosystem_service import EcosystemService


def test_real_execution_is_disabled_even_when_system_is_healthy():
    status = EcosystemService().system_status()
    assert status["execution_allowed"] is False
    assert status["execution"] == "bloqueada_por_padrao"
    assert status["real"] == "DESABILITADO"
    assert status["production_operation_gate"]["authorized"] is False
    assert status["production_operation_gate"]["real_execution"] == "DESABILITADO"


def test_unknown_component_state_is_promoted_to_critical_health():
    from core.ecosystem_health import build_health_alerts
    alerts = build_health_alerts({"arbitrary_component": "UNSAFE"})
    assert len(alerts) == 1
    assert alerts[0].severity == "CRITICAL"


def test_production_boundary_failure_is_visible_as_critical_health(monkeypatch):
    service = EcosystemService()
    policy_type = type(service.production_storage)
    monkeypatch.setattr(policy_type, "status", lambda self: {"state": "UNSAFE_TENANT_SCOPE"})
    status = service.system_status()
    assert status["health"] == "CRITICAL"
    assert any(a["component"] == "production_storage" and a["severity"] == "CRITICAL" for a in status["alerts"])
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"


def test_market_context_has_no_operational_decision_fields():
    context = reason_market_context(None)
    assert context is None



def test_security_audit_persistence_failure_is_visible_as_critical_health(monkeypatch):
    from types import SimpleNamespace
    import integration.ecosystem_service as service_module

    monkeypatch.setattr(
        service_module,
        "AUDIT",
        SimpleNamespace(
            persistence_available=False,
            persistence_error="write_failed",
            max_events=1000,
        ),
    )

    status = EcosystemService().system_status()

    assert status["health"] == "CRITICAL"
    assert status["security_audit"]["persistence"] == "WRITE_FAILED"
    assert status["components"]["security_audit"] == "WRITE_FAILED"
    assert any(
        alert["component"] == "security_audit"
        and alert["severity"] == "CRITICAL"
        for alert in status["alerts"]
    )
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
