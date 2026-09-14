from security.http_identity import TRUSTED_ROLE_KEY, TRUSTED_SUBJECT_KEY, TRUSTED_TENANT_KEY, clear_trusted_identity, require_trusted_identity
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def test_configured_service_binds_analysis_to_trusted_request_owner():
    clear_trusted_identity()
    require_trusted_identity({
        TRUSTED_SUBJECT_KEY: "user-a",
        TRUSTED_TENANT_KEY: "tenant-a",
        TRUSTED_ROLE_KEY: "user",
    })
    service = ConfiguredEcosystemService()

    record = service.analyze({"score": 90, "confirmed": True, "filters_ok": True}, persist=False)

    assert record.subject_id == "user-a"
    assert record.tenant_id == "tenant-a"
    clear_trusted_identity()
