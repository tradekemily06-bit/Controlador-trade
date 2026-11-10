from integration.ecosystem_service import EcosystemService


def test_system_status_exposes_health_and_alerts():
    status = EcosystemService().system_status()
    assert status["health"] in {"OK", "WARNING", "CRITICAL"}
    assert status["mt5_demo"] == "NOT_CONNECTED"
    assert isinstance(status["components"], dict)
    assert isinstance(status["alerts"], list)
    assert status["security_audit"]["persistence"] in {
        "NOT_CONFIGURED", "DURABLE", "UNAVAILABLE", "SCHEMA_INVALID",
        "WRITE_FAILED", "READ_FAILED",
    }
    assert status["components"]["security_audit"] in {
        "OPTIONAL", "DURABLE", "UNAVAILABLE", "SCHEMA_INVALID",
        "WRITE_FAILED", "READ_FAILED",
    }
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
