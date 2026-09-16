from security.http_identity import (
    TRUSTED_ROLE_KEY,
    TRUSTED_SUBJECT_KEY,
    TRUSTED_TENANT_KEY,
    clear_trusted_identity,
    current_trusted_identity,
    require_trusted_identity,
)


def test_trusted_identity_is_available_only_from_server_injected_wsgi_scope():
    clear_trusted_identity()
    environ = {
        TRUSTED_SUBJECT_KEY: "user-a",
        TRUSTED_TENANT_KEY: "tenant-a",
        TRUSTED_ROLE_KEY: "user",
        "HTTP_X_CONTROLADOR_SUBJECT_ID": "attacker",
        "HTTP_X_CONTROLADOR_TENANT_ID": "attacker-tenant",
    }

    identity = require_trusted_identity(environ)

    assert identity.subject_id == "user-a"
    assert identity.tenant_id == "tenant-a"
    assert identity.role == "user"
    assert current_trusted_identity() == identity
    clear_trusted_identity()
    assert current_trusted_identity() is None
