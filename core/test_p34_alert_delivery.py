from core.p33_operational_alerts import AlertSeverity, OperationalAlert, OperationalAlertReport
from core.p34_alert_delivery import AlertDelivery, AlertDeliveryMessage


class RecordingSink:
    def __init__(self):
        self.messages = []

    def deliver(self, message):
        self.messages.append(message)


def make_report():
    return OperationalAlertReport(
        alerts=(
            OperationalAlert("RUNTIME_BLOCKED", AlertSeverity.CRITICAL, "runtime", "blocked"),
            OperationalAlert("MARKET_DATA_STALE", AlertSeverity.WARNING, "market", "stale"),
        )
    )


def test_dispatch_preserves_order_and_payload():
    report = make_report()
    sink = RecordingSink()

    delivered = AlertDelivery().dispatch(report, sink)

    assert delivered == 2
    assert sink.messages == [
        AlertDeliveryMessage("RUNTIME_BLOCKED", "CRITICAL", "runtime", "blocked"),
        AlertDeliveryMessage("MARKET_DATA_STALE", "WARNING", "market", "stale"),
    ]


def test_empty_report_has_no_side_effects():
    sink = RecordingSink()

    assert AlertDelivery().dispatch(OperationalAlertReport(alerts=()), sink) == 0
    assert sink.messages == []


def test_invalid_report_is_rejected():
    sink = RecordingSink()

    try:
        AlertDelivery().dispatch(object(), sink)
    except ValueError as exc:
        assert "OperationalAlertReport" in str(exc)
    else:
        raise AssertionError("invalid report should be rejected")


def test_invalid_sink_is_rejected():
    try:
        AlertDelivery().dispatch(make_report(), object())
    except ValueError as exc:
        assert "deliver" in str(exc)
    else:
        raise AssertionError("invalid sink should be rejected")


def test_sink_failure_does_not_mutate_report():
    report = make_report()

    class FailingSink:
        def deliver(self, message):
            raise RuntimeError("destination unavailable")

    try:
        AlertDelivery().dispatch(report, FailingSink())
    except RuntimeError as exc:
        assert str(exc) == "destination unavailable"
    else:
        raise AssertionError("sink failure should propagate")

    assert report == make_report()
