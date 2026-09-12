from integration.ecosystem_service import EcosystemService
from storage.production_boundary import ProductionStoragePolicy


def test_system_status_exposes_fail_closed_production_storage():
    status = EcosystemService().system_status()
    storage = status["production_storage"]

    assert storage["state"] == "NOT_CONFIGURED"
    assert storage["required"] is True
    assert storage["tenant_scope"] == "ENFORCED"
    assert storage["durability"] == "NOT_DURABLE"
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"


def test_system_status_accepts_explicit_ready_production_storage_policy():
    policy = ProductionStoragePolicy(
        provider_configured=True,
        tenant_scoped=True,
        durable=True,
    )

    status = EcosystemService(production_storage=policy).system_status()

    assert status["production_storage"]["state"] == "READY"
    assert status["production_storage"]["provider"] == "CONFIGURED"
    assert status["production_storage"]["tenant_scope"] == "ENFORCED"
    assert status["production_storage"]["durability"] == "DURABLE"
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
