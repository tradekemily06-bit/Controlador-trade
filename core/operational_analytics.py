from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Signal
from .operation_memory import OperationMemory, OperationMemoryRecord


@dataclass(frozen=True)
class AnalyticsSnapshot:
    """Immutable operational metrics derived from validated memory records."""

    total: int
    completed: int
    pending: int
    wins: int
    losses: int
    ambiguous: int
    win_rate: float | None
    loss_streak: int
    max_loss_streak: int
    direction: dict[str, dict[str, object]]
    quality: dict[str, dict[str, object]]
    decision_distribution: dict[str, int]


class OperationalAnalytics:
    """Calcula métricas sem alterar a memória operacional."""

    def __init__(self, memory: OperationMemory) -> None:
        if not isinstance(memory, OperationMemory):
            raise TypeError("memory deve ser OperationMemory.")
        self.memory = memory

    @staticmethod
    def _in_period(
        record: OperationMemoryRecord,
        start: datetime | None,
        end: datetime | None,
    ) -> bool:
        if start is not None and record.timestamp < start:
            return False
        if end is not None and record.timestamp > end:
            return False
        return True

    def records(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[OperationMemoryRecord, ...]:
        if start is not None and end is not None and start > end:
            raise ValueError("start não pode ser posterior a end.")
        return tuple(
            record
            for record in self.memory.records()
            if self._in_period(record, start, end)
        )

    @staticmethod
    def _direction_metrics(records: list[OperationMemoryRecord]) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for signal in (Signal.COMPRA, Signal.VENDA):
            items = [r for r in records if r.signal is signal and r.result in {"WIN", "LOSS"}]
            wins = sum(r.result == "WIN" for r in items)
            result[signal.value] = {
                "total": len(items),
                "wins": wins,
                "losses": len(items) - wins,
                "win_rate": wins / len(items) if items else None,
            }
        return result

    @staticmethod
    def _quality_metrics(records: list[OperationMemoryRecord]) -> dict[str, dict[str, object]]:
        levels = sorted({r.quality_level for r in records if r.quality_level is not None})
        result: dict[str, dict[str, object]] = {}
        for level in levels:
            items = [
                r for r in records
                if r.quality_level == level and r.result in {"WIN", "LOSS"}
            ]
            wins = sum(r.result == "WIN" for r in items)
            result[level] = {
                "total": len(items),
                "wins": wins,
                "losses": len(items) - wins,
                "win_rate": wins / len(items) if items else None,
            }
        return result

    def snapshot(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> AnalyticsSnapshot:
        selected = list(self.records(start=start, end=end))
        completed = [r for r in selected if r.result in {"WIN", "LOSS"}]
        wins = sum(r.result == "WIN" for r in completed)
        losses = sum(r.result == "LOSS" for r in completed)
        ambiguous = sum(r.result == "AMBOS" for r in selected)

        current_streak = 0
        max_loss_streak = 0
        for record in completed:
            if record.result == "LOSS":
                current_streak += 1
                max_loss_streak = max(max_loss_streak, current_streak)
            else:
                current_streak = 0

        distribution = {
            decision: sum(r.decision == decision for r in selected)
            for decision in ("EXECUTAR", "BLOQUEAR", "AGUARDAR")
        }
        return AnalyticsSnapshot(
            total=len(selected),
            completed=len(completed),
            pending=sum(r.result == "PENDENTE" for r in selected),
            wins=wins,
            losses=losses,
            ambiguous=ambiguous,
            win_rate=wins / len(completed) if completed else None,
            loss_streak=current_streak,
            max_loss_streak=max_loss_streak,
            direction=self._direction_metrics(selected),
            quality=self._quality_metrics(selected),
            decision_distribution=distribution,
        )
