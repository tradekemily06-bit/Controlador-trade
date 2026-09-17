from __future__ import annotations

from datetime import datetime, timezone

from audit.events import AuditEvent, AuditEventType, AuditLogger
from audit.execution_audit import ExecutionAuditEvent, ExecutionAuditLog
from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity
from core.observability_redaction import REDACTED, redact, redact_event, redact_text
from core.p21_observability import HealthState, RuntimeHealthMonitor, RecoveryState
from execution.execution_lifecycle import ExecutionLifecycleState


def test_redaction_recurses_without_mutating_input():
    original = {
        "request_id": "req-1",
        "authorization": "Bearer secret-token",
        "nested": {"api_key": "abc", "symbol": "EURUSD"},
        "items": [{"password": "pw", "value": 3}],
        "diagnostic": "authorization=hidden-token",
    }

    safe = redact(original)

    assert safe["authorization"] == REDACTED
    assert safe["nested"]["api_key"] == REDACTED
    assert safe["items"][0]["password"] == REDACTED
    assert safe["nested"]["symbol"] == "EURUSD"
    assert REDACTED in safe["diagnostic"]
    assert original["authorization"] == "Bearer secret-token"


def test_redaction_drops_bytes_and_exception_payloads():
    secret_bytes = b"Bearer opaque-secret-token"
    secret_exception = RuntimeError("authorization=opaque-secret-token")

    safe = redact({"body": secret_bytes, "error": secret_exception})

    assert safe["body"] == REDACTED
    assert safe["error"] == "RuntimeError"
    assert "opaque-secret-token" not in repr(safe)


def test_redaction_closes_json_and_url_credential_bypasses():
    text = 'payload={"token": "json-secret", "password": "pw-secret"} https://example.test/callback?access_token=url-secret&symbol=EURUSD'
    safe = redact_text(text)

    assert "json-secret" not in safe
    assert "pw-secret" not in safe
    assert "url-secret" not in safe
    assert safe.count(REDACTED) == 3
    assert "symbol=EURUSD" in safe


def test_event_boundary_requires_type_and_mapping():
    event = redact_event(event_type="EXECUTION_BLOCKED", payload={"token": "hidden", "reason": "kill-switch"})
    assert event["event_type"] == "EXECUTION_BLOCKED"
    assert event["payload"]["token"] == REDACTED


def test_audit_logger_redacts_structured_and_free_form_diagnostics():
    event = AuditEvent(
        AuditEventType.ERROR,
        "falha authorization=super-secret",
        datetime.now(timezone.utc),
        {"api_key": "abc", "symbol": "EURUSD"},
        "req-1",
    )
    logger = AuditLogger()
    logger.record(event)
    stored = logger.events()[0]
    assert stored.request_id == "req-1"
    assert REDACTED in stored.message
    assert stored.data["api_key"] == REDACTED
    assert stored.data["symbol"] == "EURUSD"


def test_execution_audit_redacts_messages():
    event = ExecutionAuditEvent(
        "req-1",
        ExecutionLifecycleState.REJECTED,
        datetime.now(timezone.utc),
        "rejected password=super-secret",
    )
    audit = ExecutionAuditLog()
    audit.append(event)
    assert REDACTED in audit.events()[0].message


def test_global_notifications_are_durable_and_visible_to_scoped_users(tmp_path):
    from security.http_identity import clear_trusted_identity, require_trusted_identity
    from storage.scoped_state_store import SQLiteScopedStateStore

    state = SQLiteScopedStateStore(tmp_path / "state.db")
    center = EcosystemNotificationCenter(state_store=state, require_durable=True)
    center.publish_global(EcosystemNotification("global-1", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "Update", "authorization=hidden"))
    try:
        require_trusted_identity({
            "PATH_INFO": "/api/notifications",
            "controlador.trusted_tenant_id": "tenant-a",
            "controlador.trusted_subject_id": "user-a",
            "controlador.trusted_role": "user",
        })
        visible = EcosystemNotificationCenter(state_store=state, require_durable=True).all()
        assert [item.notification_id for item in visible] == ["global-1"]
        assert REDACTED in visible[0].message
    finally:
        clear_trusted_identity()


def test_health_states_are_observational_not_authorization_states():
    assert {HealthState.HEALTHY.value, HealthState.ATTENTION.value, HealthState.BLOCKED.value} == {
        "HEALTHY",
        "ATTENTION",
        "BLOCKED",
    }


def test_health_monitor_fails_closed_when_persisted_state_is_unavailable():
    class BrokenLedger:
        def records(self):
            raise OSError("ledger indisponível")

    monitor = RuntimeHealthMonitor.__new__(RuntimeHealthMonitor)
    monitor.ledger = BrokenLedger()
    health = monitor.assess()

    assert health.state is HealthState.BLOCKED
    assert health.recovery_state is RecoveryState.INVALID
    assert health.ledger_entries == 0
    assert "OSError" in health.message
