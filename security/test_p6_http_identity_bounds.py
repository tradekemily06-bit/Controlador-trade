from security.http_identity import TrustedHttpIdentity


def test_trusted_identity_rejects_oversized_or_control_character_components():
    assert not TrustedHttpIdentity("x" * 257, "tenant", "user").is_valid()
    assert not TrustedHttpIdentity("user", "t" * 257, "user").is_valid()
    assert not TrustedHttpIdentity("user", "tenant", "r" * 65).is_valid()
    assert not TrustedHttpIdentity("user\nattacker", "tenant", "user").is_valid()
