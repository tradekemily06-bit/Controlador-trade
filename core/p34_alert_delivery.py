from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.p33_operational_alerts import OperationalAlert, OperationalAlertReport


@dataclass(frozen=True)
class AlertDeliveryMessage:
    """Immutable transport-neutral representation of one operational alert."""

    code: str
    severity: str
    source: str
    message: str

    @classmethod
    def from_alert(cls, alert: OperationalAlert) -> "AlertDeliveryMessage":
        if not isinstance(alert, OperationalAlert):
            raise ValueError("alert must be an OperationalAlert")
        return cls(
            code=alert.code,
            severity=alert.severity.value,
            source=alert.source,
            message=alert.message,
        )


class AlertSink(Protocol):
    """Destination boundary; implementations may live outside the core."""

    def deliver(self, message: AlertDeliveryMessage) -> None:
        ...


class AlertDelivery:
    """Dispatches P33 alerts to an abstract sink without external I/O."""

    def dispatch(self, report: OperationalAlertReport, sink: AlertSink) -> int:
        if not isinstance(report, OperationalAlertReport):
            raise ValueError("report must be an OperationalAlertReport")
        if not hasattr(sink, "deliver") or not callable(sink.deliver):
            raise ValueError("sink must provide a callable deliver(message) method")

        delivered = 0
        for alert in report.alerts:
            sink.deliver(AlertDeliveryMessage.from_alert(alert))
            delivered += 1
        return delivered
