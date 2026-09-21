import io
import json
import os

from app import application


def _request(path, method="GET", *, trusted=None, spoofed=None, payload=None):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json" if payload is not None else "",
        "REMOTE_ADDR": "p6-test-client",
        "wsgi.input": io.BytesIO(body),
    }
    if trusted is not None:
        subject, tenant, role = trusted
        environ["controlador.trusted_subject_id"] = subject
        environ["controlador.trusted_tenant_id"] = tenant
        environ["controlador.trusted_role"] = role
    if spoofed is not None:
        subject, tenant, role = spoofed
        environ["HTTP_X_TRUSTED_SUBJECT_ID"] = subject
        environ["HTTP_X_TRUSTED_TENANT_ID"] = tenant
        environ["HTTP_X_TRUSTED_ROLE"] = role

    result = b"".join(application(environ, start_response))
    return captured["status"], result


def _with_public_saas():
    old = os.environ.get("CONTROLADOR_SAAS_PUBLIC")
    os.environ["CONTROLADOR_SAAS_PUBLIC"] = "1"
    return old


def _restore_public_saas(old):
    if old is None:
        os.environ.pop("CONTROLADOR_SAAS_PUBLIC", None)
    else:
        os.environ["CONTROLADOR_SAAS_PUBLIC"] = old


def test_trusted_identity_is_cleared_between_sequential_requests():
    old = _with_public_saas()
    try:
        first_status, _ = _request(
            "/api/memory",
            trusted=("user-a", "tenant-a", "member"),
        )
        second_status, _ = _request("/api/memory")
        assert first_status == "503 Service Unavailable"
        assert second_status == "403 Forbidden"
    finally:
        _restore_public_saas(old)


def test_browser_headers_cannot_establish_trusted_identity_for_any_owner_route():
    old = _with_public_saas()
    try:
        status, _ = _request(
            "/api/statistics",
            spoofed=("attacker", "attacker-tenant", "admin"),
        )
        assert status == "403 Forbidden"
    finally:
        _restore_public_saas(old)


def test_unknown_saas_route_fails_closed_even_with_trusted_identity():
    old = _with_public_saas()
    try:
        status, _ = _request(
            "/api/memory/",
            trusted=("user-a", "tenant-a", "member"),
        )
        assert status == "503 Service Unavailable"
    finally:
        _restore_public_saas(old)


def test_unknown_method_variant_does_not_bypass_saas_route_matrix():
    old = _with_public_saas()
    try:
        status, _ = _request(
            "/api/analyze",
            method="PUT",
            trusted=("user-a", "tenant-a", "member"),
        )
        assert status == "503 Service Unavailable"
    finally:
        _restore_public_saas(old)
