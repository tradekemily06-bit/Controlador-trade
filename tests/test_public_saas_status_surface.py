import os

from integration.ecosystem_service import EcosystemService


def test_public_status_does_not_expose_internal_runtime_or_storage_details():
    service = EcosystemService()
    status = service.public_status()
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
    assert "production_storage" not in status
    assert "production_operation_gate" not in status
    assert "operational_observability" not in status
    assert "alerts" in status


def test_public_saas_status_is_explicitly_safe(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "1")
    status = EcosystemService().public_status()
    assert status["execution_allowed"] is False
    assert status["health"] == "SAFE"
    assert status["real"] == "DESABILITADO"
    assert status["alerts"] == []
    assert not any(key in status for key in ("memory_persistence", "production_storage", "production_operation_gate", "operational_observability"))
