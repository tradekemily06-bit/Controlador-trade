from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from security.http_identity import clear_trusted_identity, require_trusted_identity


def _identity(subject: str, tenant: str) -> None:
    require_trusted_identity(
        {
            "controlador.trusted_subject_id": subject,
            "controlador.trusted_tenant_id": tenant,
            "controlador.trusted_role": "user",
        }
    )


def test_preferences_are_isolated_between_tenant_subject_scopes():
    clear_trusted_identity()
    service = ConfiguredEcosystemService()

    _identity("user-a", "tenant-a")
    service.update_preferences({"default_symbol": "GBPUSD"})
    assert service.get_preferences()["default_symbol"] == "GBPUSD"

    _identity("user-b", "tenant-b")
    assert service.get_preferences()["default_symbol"] == "EURUSD"
    service.update_preferences({"default_symbol": "USDJPY"})

    _identity("user-a", "tenant-a")
    assert service.get_preferences()["default_symbol"] == "GBPUSD"
    _identity("user-b", "tenant-b")
    assert service.get_preferences()["default_symbol"] == "USDJPY"
    clear_trusted_identity()


def test_notifications_are_isolated_but_global_events_are_visible_to_all():
    clear_trusted_identity()
    service = ConfiguredEcosystemService()
    service.publish_ecosystem_update("Atualização global", "Atualização do ecossistema.")

    _identity("user-a", "tenant-a")
    service.publish_material_event("RISK", "Risco A", "Evento privado A.")
    titles_a = {item["title"] for item in service.all_notifications()}
    assert {"Atualização global", "Risco A"} <= titles_a

    _identity("user-b", "tenant-b")
    titles_b = {item["title"] for item in service.all_notifications()}
    assert "Atualização global" in titles_b
    assert "Risco A" not in titles_b
    service.publish_material_event("RISK", "Risco B", "Evento privado B.")

    _identity("user-a", "tenant-a")
    titles_a_again = {item["title"] for item in service.all_notifications()}
    assert "Risco A" in titles_a_again
    assert "Risco B" not in titles_a_again
    clear_trusted_identity()
