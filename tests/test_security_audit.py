from security_audit import SecurityAudit, _sanitize_path


def test_security_audit_redacts_common_sensitive_path_segments():
    path = (
        "/api/fiscal/123456/"
        "550e8400-e29b-41d4-a716-446655440000/"
        "person@example.com/"
        "0123456789abcdef0123456789abcdef"
        "?access_token=must-not-be-kept"
    )

    assert _sanitize_path(path) == (
        "/api/fiscal/<redacted>/<redacted>/<redacted>/<redacted>"
    )


def test_security_audit_rejects_non_absolute_path_values():
    assert _sanitize_path("https://example.test/private") == "/<invalid>"


def test_security_audit_record_keeps_only_bounded_safe_event_fields():
    audit = SecurityAudit(max_events=2)
    audit.record(
        request_id="request-1",
        method="POST",
        path="/api/fiscal/987654321",
        status=403,
        client_key="198.51.100.42",
    )

    events = audit.snapshot()
    assert len(events) == 1
    assert events[0]["path"] == "/api/fiscal/<redacted>"
    assert set(events[0]) == {
        "timestamp",
        "request_id",
        "method",
        "path",
        "status",
        "client_hash",
    }
    assert "198.51.100.42" not in str(events[0])
