from trusted_identity import trusted_identity_from_headers


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
