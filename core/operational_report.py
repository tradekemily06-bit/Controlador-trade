from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.operation_memory import OperationMemory, OperationMemoryRecord
from core.operational_analytics import AnalyticsSnapshot, OperationalAnalytics


@dataclass(frozen=True)
class OperationalReport:
    """Immutable report combining analytics with the underlying records."""

    generated_at: datetime
    snapshot: AnalyticsSnapshot
    records: tuple[OperationMemoryRecord, ...]


class OperationalReporter:
    """Builds read-only operational reports from validated memory."""

    def __init__(self, memory: OperationMemory) -> None:
        if memory is None:
            raise ValueError("memory é obrigatória.")
        self.memory = memory
        self.analytics = OperationalAnalytics(memory)

    def report(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> OperationalReport:
        records = tuple(self.analytics.records(start=start, end=end))
        snapshot = self.analytics.snapshot(start=start, end=end)
        return OperationalReport(
            generated_at=datetime.now().astimezone(),
            snapshot=snapshot,
            records=records,
        )
