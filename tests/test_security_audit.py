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



def test_security_audit_persists_only_the_newest_events_across_restart(tmp_path):
    database = tmp_path / "audit.sqlite3"
    first = SecurityAudit(max_events=2, database_path=str(database))

    for index in range(3):
        first.record(
            request_id=f"request-{index}",
            method="GET",
            path=f"/api/events/{index}",
            status=200,
            client_key=f"client-{index}",
        )

    assert first.persistence_available is True
    assert first.persistence_error is None

    restarted = SecurityAudit(max_events=2, database_path=str(database))
    events = restarted.snapshot()

    assert [event["request_id"] for event in events] == ["request-1", "request-2"]
    assert restarted.persistence_available is True


def test_security_audit_reports_invalid_existing_schema_without_leaking_details(tmp_path):
    import sqlite3

    database = tmp_path / "malformed.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE security_events (id INTEGER PRIMARY KEY, secret_path TEXT)")

    audit = SecurityAudit(max_events=2, database_path=str(database))

    assert audit.persistence_available is False
    assert audit.persistence_error == "schema_invalid"

    audit.record(
        request_id="request-safe",
        method="GET",
        path="/api/health",
        status=200,
        client_key="client",
    )
    assert audit.snapshot()[0]["request_id"] == "request-safe"
    assert str(database) not in str(audit.snapshot())
