from __future__ import annotations

from security.wsgi_identity import trusted_tenant_context_from_wsgi


def test_wsgi_identity_ignores_client_supplied_http_headers():
    environ = {
        "HTTP_X_TENANT_ID": "tenant-attacker",
        "HTTP_X_USER_ID": "attacker",
        "HTTP_X_IDENTITY_VERIFIED": "true",
        "HTTP_REMOTE_USER": "attacker",
    }

    assert trusted_tenant_context_from_wsgi(
        environ, middleware_enabled=True
    ) is None


def test_wsgi_identity_requires_server_injected_verified_context():
    base = {
        "REMOTE_USER": "alice",
        "controlador.tenant_id": "tenant-a",
        "controlador.identity_verified": True,
    }

    context = trusted_tenant_context_from_wsgi(base, middleware_enabled=True)
    assert context is not None
    assert context.tenant_id == "tenant-a"
    assert context.subject_id == "alice"

    for changed in (
        {**base, "controlador.identity_verified": "true"},
        {**base, "REMOTE_USER": "alice\nattacker"},
        {**base, "controlador.tenant_id": "tenant-" + "x" * 300},
    ):
        assert trusted_tenant_context_from_wsgi(
            changed, middleware_enabled=True
        ) is None


def test_wsgi_identity_is_disabled_without_explicit_middleware_setting():
    environ = {
        "REMOTE_USER": "alice",
        "controlador.tenant_id": "tenant-a",
        "controlador.identity_verified": True,
    }
    assert trusted_tenant_context_from_wsgi(
        environ, middleware_enabled=False
    ) is None
