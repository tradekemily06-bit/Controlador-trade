from integration.ecosystem_service import EcosystemService


def test_system_status_exposes_health_and_alerts():
    status = EcosystemService().system_status()
    assert status["health"] in {"OK", "WARNING"}
    assert isinstance(status["components"], dict)
    assert isinstance(status["alerts"], list)
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
