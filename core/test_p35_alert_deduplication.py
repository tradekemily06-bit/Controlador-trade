import pytest

from core.p33_operational_alerts import AlertSeverity, OperationalAlert, OperationalAlertReport
from core.p35_alert_deduplication import AlertDeduplicator


class RecordingSink:
    def __init__(self):
        self.messages = []

    def deliver(self, message):
        self.messages.append(message)


def alert(code="RUNTIME_BLOCKED", message="runtime blocked"):
    return OperationalAlert(
        code=code,
        severity=AlertSeverity.CRITICAL,
        source="runtime",
        message=message,
    )


def test_first_alert_is_delivered():
    sink = RecordingSink()
    result = AlertDeduplicator().dispatch(OperationalAlertReport((alert(),)), sink)

    assert result.received == 1
    assert result.delivered == 1
    assert result.suppressed == 0
    assert len(sink.messages) == 1


def test_same_alert_in_next_report_is_suppressed():
    sink = RecordingSink()
    deduplicator = AlertDeduplicator()
    report = OperationalAlertReport((alert(),))

    deduplicator.dispatch(report, sink)
    result = deduplicator.dispatch(report, sink)

    assert result.delivered == 0
    assert result.suppressed == 1
    assert len(sink.messages) == 1


def test_changed_alert_is_delivered_again():
    sink = RecordingSink()
    deduplicator = AlertDeduplicator()

    deduplicator.dispatch(OperationalAlertReport((alert(),)), sink)
    result = deduplicator.dispatch(
        OperationalAlertReport((alert(message="runtime still blocked for a new reason"),)),
        sink,
    )

    assert result.delivered == 1
    assert result.suppressed == 0
    assert len(sink.messages) == 2


def test_alert_reappearing_after_absence_is_not_suppressed():
    sink = RecordingSink()
    deduplicator = AlertDeduplicator()
    first = OperationalAlertReport((alert(),))
    empty = OperationalAlertReport(())

    deduplicator.dispatch(first, sink)
    deduplicator.dispatch(empty, sink)
    result = deduplicator.dispatch(first, sink)

    assert result.delivered == 1
    assert result.suppressed == 0
    assert len(sink.messages) == 2


def test_order_is_preserved_for_distinct_alerts():
    sink = RecordingSink()
    deduplicator = AlertDeduplicator()
    report = OperationalAlertReport(
        alerts=(
            alert("RUNTIME_BLOCKED", "a"),
            alert("MARKET_DATA_INVALID", "b"),
        )
    )

    result = deduplicator.dispatch(report, sink)

    assert result.delivered == 2
    assert [message.code for message in sink.messages] == [
        "RUNTIME_BLOCKED",
        "MARKET_DATA_INVALID",
    ]


def test_invalid_inputs_fail_closed():
    deduplicator = AlertDeduplicator()
    sink = RecordingSink()

    with pytest.raises(ValueError):
        deduplicator.dispatch("invalid", sink)
    with pytest.raises(ValueError):
        deduplicator.dispatch(OperationalAlertReport(()), object())
