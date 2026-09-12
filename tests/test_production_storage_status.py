from integration.ecosystem_service import EcosystemService


def test_system_status_exposes_fail_closed_production_storage():
    status = EcosystemService().system_status()
    storage = status["production_storage"]

    assert storage["state"] == "NOT_CONFIGURED"
    assert storage["required"] is True
    assert storage["tenant_scope"] == "ENFORCED"
    assert storage["durability"] == "NOT_DURABLE"
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
