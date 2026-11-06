from streamlit_panel.trusted_identity import trusted_identity_from_headers


def test_trusted_identity_header_lookup_is_case_insensitive():
    headers = {"cF-aCcEsS-aUtHeNtIcAtEd-UsEr-eMaIl": "owner@example.com"}
    assert trusted_identity_from_headers(
        headers, "Cf-Access-Authenticated-User-Email"
    ) == "owner@example.com"


def test_trusted_identity_header_lookup_trims_configured_name_and_value():
    assert trusted_identity_from_headers(
        {"X-Auth-User": " owner@example.com "}, " X-Auth-User "
    ) == "owner@example.com"


def test_trusted_identity_header_lookup_fails_closed_for_conflicting_duplicates():
    headers = {
        "X-Auth-User": "owner@example.com",
        "x-auth-user": "attacker@example.com",
    }
    assert trusted_identity_from_headers(headers, "X-Auth-User") == ""


def test_trusted_identity_header_lookup_rejects_missing_or_non_string_values():
    assert trusted_identity_from_headers({}, "X-Auth-User") == ""
    assert trusted_identity_from_headers({"X-Auth-User": ["owner@example.com"]}, "X-Auth-User") == ""
    assert trusted_identity_from_headers({"X-Auth-User": "owner@example.com"}, "") == ""


def test_trusted_identity_header_lookup_rejects_malformed_duplicate_even_with_valid_value():
    headers = {
        "X-Auth-User": "owner@example.com",
        "x-auth-user": None,
    }
    assert trusted_identity_from_headers(headers, "X-Auth-User") == ""


def test_trusted_identity_header_lookup_accepts_identical_duplicate_spellings():
    headers = {
        "X-Auth-User": " owner@example.com ",
        "x-auth-user": "owner@example.com",
    }
    assert trusted_identity_from_headers(headers, "X-Auth-User") == "owner@example.com"


def test_trusted_identity_ignores_unconfigured_forwarding_and_auth_aliases():
    headers = {
        "X-Forwarded-Email": "attacker@example.com",
        "X-Auth-Request-Email": "attacker@example.com",
        "Remote-User": "attacker@example.com",
        "Authorization": "Bearer attacker-token",
    }
    assert trusted_identity_from_headers(
        headers, "Cf-Access-Authenticated-User-Email"
    ) == ""


def test_trusted_identity_uses_only_the_exact_configured_header():
    headers = {
        "Cf-Access-Authenticated-User-Email": "owner@example.com",
        "X-Forwarded-Email": "attacker@example.com",
        "X-Auth-Request-Email": "attacker@example.com",
        "Remote-User": "attacker@example.com",
    }
    assert trusted_identity_from_headers(
        headers, "Cf-Access-Authenticated-User-Email"
    ) == "owner@example.com"
