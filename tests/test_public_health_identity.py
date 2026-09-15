from security.http_identity import clear_trusted_identity, current_trusted_identity, require_trusted_identity


def test_public_health_identity_is_non_user_and_non_tenant():
    clear_trusted_identity()
    identity = require_trusted_identity({"PATH_INFO": "/api/health"})

    assert identity.subject_id == "health-check"
    assert identity.tenant_id == "health-check"
    assert identity.role == "health"
    assert current_trusted_identity() == identity
    clear_trusted_identity()
    assert current_trusted_identity() is None


def test_non_health_requests_still_require_real_trusted_identity():
    clear_trusted_identity()
    try:
        require_trusted_identity({"PATH_INFO": "/api/status"})
    except PermissionError:
        pass
    else:
        raise AssertionError("non-health public request must require trusted identity")
