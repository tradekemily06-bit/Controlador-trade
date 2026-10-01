from security_audit import SecurityAudit

def test_security_audit_survives_restart(tmp_path):
    path = tmp_path / "security.sqlite"
    first = SecurityAudit(database_path=str(path))
    first.record(request_id="req-1", method="POST", path="/api/runtime/cycle", status=200, client_key="client")
    second = SecurityAudit(database_path=str(path))
    events = second.snapshot()
    assert len(events) == 1
    assert events[0]["request_id"] == "req-1"
    assert events[0]["path"] == "/api/runtime/cycle"
