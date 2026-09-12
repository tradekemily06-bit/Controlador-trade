from core.ecosystem_health import build_health_alerts
from integration.ecosystem_service import EcosystemService


def test_healthy_components_have_no_alerts():
    assert build_health_alerts({"decision_engine": "ONLINE", "real": "DESABILITADO"}) == []


def test_warning_component_creates_visible_alert():
    alerts = build_health_alerts({"news": "AGUARDANDO_FONTE"})
    assert len(alerts) == 1
    assert alerts[0].severity == "WARNING"
    assert alerts[0].component == "news"


def test_unknown_component_state_is_critical():
    alerts = build_health_alerts({"decision_engine": "OFFLINE"})
    assert alerts[0].severity == "CRITICAL"


def test_system_status_exposes_health_and_keeps_execution_blocked():
    status = EcosystemService().system_status()
    assert status["health"] in {"WARNING", "CRITICAL"}
    assert isinstance(status["alerts"], list)
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
