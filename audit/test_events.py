from datetime import datetime, timezone

import pytest

from audit.events import AuditEvent, AuditEventType, AuditLogger


def test_audit_event_records_basic_information():
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

    event = AuditEvent(
        event_type=AuditEventType.DECISION,
        message="Decisão aguardando confirmação.",
        timestamp=timestamp,
        data={"score": 70},
    )

    assert event.event_type == AuditEventType.DECISION
    assert event.message == "Decisão aguardando confirmação."
    assert event.timestamp == timestamp
    assert event.data["score"] == 70


def test_audit_logger_records_events():
    logger = AuditLogger()

    event = AuditEvent(
        event_type=AuditEventType.ANALYSIS,
        message="Análise concluída.",
    )

    logger.record(event)

    assert logger.events() == (event,)


def test_audit_logger_events_are_read_only():
    logger = AuditLogger()

    event = AuditEvent(
        event_type=AuditEventType.RISK,
        message="Risco avaliado.",
    )

    logger.record(event)

    events = logger.events()

    assert isinstance(events, tuple)
    assert len(events) == 1


def test_audit_event_requires_message():
    with pytest.raises(ValueError):
        AuditEvent(
            event_type=AuditEventType.ERROR,
            message="   ",
        )


def test_audit_event_requires_timezone():
    with pytest.raises(ValueError):
        AuditEvent(
            event_type=AuditEventType.ERROR,
            message="Erro.",
            timestamp=datetime(2026, 1, 1),
        )


def test_audit_logger_clear():
    logger = AuditLogger()

    logger.record(
        AuditEvent(
            event_type=AuditEventType.EXECUTION,
            message="Execução registrada.",
        )
    )

    logger.clear()

    assert logger.events() == ()
