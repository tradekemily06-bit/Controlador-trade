from security_audit import SecurityAudit


def test_audit_records_without_raw_client_identifier():
    audit = SecurityAudit(max_events=3)
    audit.record(request_id="req-1", method="GET", path="/api/health", status=200, client_key="10.0.0.1")
    event = audit.snapshot()[0]
    assert event["request_id"] == "req-1"
    assert event["status"] == 200
    assert event["path"] == "/api/health"
    assert event["client_hash"] != "10.0.0.1"
    assert len(event["client_hash"]) == 64


def test_audit_is_bounded():
    audit = SecurityAudit(max_events=2)
    for i in range(3):
        audit.record(request_id=f"req-{i}", method="GET", path="/", status=200, client_key="client")
    events = audit.snapshot()
    assert len(events) == 2
    assert [event["request_id"] for event in events] == ["req-1", "req-2"]


def test_audit_persists_across_instances(tmp_path):
    database = tmp_path / "security-audit.sqlite3"
    first = SecurityAudit(max_events=2, database_path=str(database))
    first.record(request_id="req-1", method="POST", path="/api/analyze", status=400, client_key="client")

    second = SecurityAudit(max_events=2, database_path=str(database))
    second.record(request_id="req-2", method="GET", path="/api/status", status=200, client_key="client")

    events = second.snapshot()
    assert [event["request_id"] for event in events] == ["req-1", "req-2"]


def test_persistent_audit_retention_is_bounded(tmp_path):
    database = tmp_path / "security-audit.sqlite3"
    audit = SecurityAudit(max_events=2, database_path=str(database))
    for i in range(3):
        audit.record(request_id=f"req-{i}", method="GET", path="/", status=200, client_key="client")

    events = audit.snapshot()
    assert len(events) == 2
    assert [event["request_id"] for event in events] == ["req-1", "req-2"]
