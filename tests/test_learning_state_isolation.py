from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from security.http_identity import clear_trusted_identity, require_trusted_identity


def _identity(tenant: str, subject: str) -> None:
    require_trusted_identity(
        {
            "controlador.trusted_tenant_id": tenant,
            "controlador.trusted_subject_id": subject,
            "controlador.trusted_role": "user",
        }
    )


def test_learning_state_isolated_between_tenants() -> None:
    service = ConfiguredEcosystemService()
    try:
        _identity("tenant-a", "user-a")
        service.add_learning_resource({"resource_id": "res-a", "title": "A", "content_type": "NOTE"})
        service.add_learning_activity({"activity_id": "act-a", "prompt": "A"})
        service.add_learning_attempt({"activity_id": "act-a", "answer": "ok"})

        _identity("tenant-b", "user-b")
        assert service.learning_resources_view() == []
        assert service.learning_activities_view() == []
        assert service.learning_summary()["attempts"] == []

        service.add_learning_resource({"resource_id": "res-b", "title": "B", "content_type": "NOTE"})
        assert [item["resource_id"] for item in service.learning_resources_view()] == ["res-b"]
    finally:
        clear_trusted_identity()


def test_learning_source_cannot_be_validated_from_another_scope() -> None:
    service = ConfiguredEcosystemService()
    try:
        _identity("tenant-a", "user-a")
        service.screen_learning_source({"source_id": "source-a", "source_type": "LINK", "uri": "https://example.com/a"})
        source = service.learning_sources_view()[0]

        _identity("tenant-b", "user-b")
        import pytest
        with pytest.raises(ValueError, match="tenant atual"):
            service.validate_learning_source(type("Source", (), {"source_id": source["source_id"]})(), content_verified=True, security_checked=True)
    finally:
        clear_trusted_identity()
