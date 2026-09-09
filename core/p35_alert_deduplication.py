from __future__ import annotations

from dataclasses import dataclass

from core.p34_alert_delivery import AlertDelivery, AlertDeliveryMessage, AlertSink
from core.p33_operational_alerts import OperationalAlert, OperationalAlertReport


@dataclass(frozen=True)
class AlertDeduplicationResult:
    """Result of one deterministic alert dispatch attempt."""

    received: int
    delivered: int
    suppressed: int


class AlertDeduplicator:
    """Suppresses only consecutive identical alert messages."""

    def __init__(self) -> None:
        self._last_keys: set[tuple[str, str, str, str]] = set()

    @staticmethod
    def _key(alert: OperationalAlert) -> tuple[str, str, str, str]:
        return (alert.code, alert.severity.value, alert.source, alert.message)

    def dispatch(self, report: OperationalAlertReport, sink: AlertSink) -> AlertDeduplicationResult:
        if not isinstance(report, OperationalAlertReport):
            raise ValueError("report must be an OperationalAlertReport")
        if not hasattr(sink, "deliver") or not callable(sink.deliver):
            raise ValueError("sink must provide a callable deliver(message) method")

        delivered = 0
        suppressed = 0
        current_keys: set[tuple[str, str, str, str]] = set()
        delivery = AlertDelivery()

        for alert in report.alerts:
            key = self._key(alert)
            current_keys.add(key)
            if key in self._last_keys:
                suppressed += 1
                continue
            delivery.dispatch(
                OperationalAlertReport(alerts=(alert,)),
                sink,
            )
            delivered += 1

        self._last_keys = current_keys
        return AlertDeduplicationResult(
            received=len(report.alerts),
            delivered=delivered,
            suppressed=suppressed,
        )
