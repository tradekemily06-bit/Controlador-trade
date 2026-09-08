from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .models import Signal


class MemoryValidationError(ValueError):
    """Raised when an operation memory record is incomplete or invalid."""


_VALID_RESULTS = {"WIN", "LOSS", "AMBOS", "PENDENTE"}


@dataclass(frozen=True)
class OperationMemoryRecord:
    timestamp: datetime
    signal: Signal
    score: float
    decision: str
    reason: str
    result: str = "PENDENTE"
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    quality_score: Optional[float] = None
    quality_level: Optional[str] = None
    entry_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise MemoryValidationError("timestamp deve ser datetime.")
        if not isinstance(self.signal, Signal):
            raise MemoryValidationError("signal inválido.")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise MemoryValidationError("score deve ser numérico.")
        if self.score != self.score or self.score in (float("inf"), float("-inf")):
            raise MemoryValidationError("score deve ser finito.")
        if not isinstance(self.decision, str) or not self.decision.strip():
            raise MemoryValidationError("decision é obrigatória.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise MemoryValidationError("reason é obrigatório.")
        if self.result not in _VALID_RESULTS:
            raise MemoryValidationError("resultado inválido.")
        if self.quality_score is not None:
            if isinstance(self.quality_score, bool) or not isinstance(self.quality_score, (int, float)):
                raise MemoryValidationError("quality_score deve ser numérico.")
            if self.quality_score != self.quality_score or self.quality_score in (float("inf"), float("-inf")):
                raise MemoryValidationError("quality_score deve ser finito.")
        if not isinstance(self.entry_conditions, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.entry_conditions
        ):
            raise MemoryValidationError("entry_conditions deve ser uma tupla de textos não vazios.")


class OperationMemory:
    """Memória em processo; somente registros validados são armazenados."""

    def __init__(self) -> None:
        self._records: list[OperationMemoryRecord] = []

    def append(self, record: OperationMemoryRecord) -> None:
        if not isinstance(record, OperationMemoryRecord):
            raise TypeError("record deve ser OperationMemoryRecord.")
        if self._records and record.timestamp < self._records[-1].timestamp:
            raise MemoryValidationError("registros de memória devem ser cronológicos.")
        self._records.append(record)

    def records(self) -> tuple[OperationMemoryRecord, ...]:
        return tuple(self._records)

    def pending(self) -> tuple[OperationMemoryRecord, ...]:
        return tuple(r for r in self._records if r.result == "PENDENTE")

    def completed(self) -> tuple[OperationMemoryRecord, ...]:
        return tuple(r for r in self._records if r.result != "PENDENTE")

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self._records),
            "win": sum(r.result == "WIN" for r in self._records),
            "loss": sum(r.result == "LOSS" for r in self._records),
            "ambos": sum(r.result == "AMBOS" for r in self._records),
            "pendente": sum(r.result == "PENDENTE" for r in self._records),
            "compra": sum(r.signal is Signal.COMPRA for r in self._records),
            "venda": sum(r.signal is Signal.VENDA for r in self._records),
            "aguardar": sum(r.signal is Signal.AGUARDAR for r in self._records),
        }

    def metrics(self) -> dict[str, object]:
        completed = [r for r in self._records if r.result in {"WIN", "LOSS"}]
        wins = sum(r.result == "WIN" for r in completed)
        losses = sum(r.result == "LOSS" for r in completed)
        direction = {}
        for signal in (Signal.COMPRA, Signal.VENDA):
            items = [r for r in completed if r.signal is signal]
            direction[signal.value] = {
                "total": len(items),
                "wins": sum(r.result == "WIN" for r in items),
                "losses": sum(r.result == "LOSS" for r in items),
                "win_rate": (sum(r.result == "WIN" for r in items) / len(items)) if items else None,
            }
        current_streak = 0
        max_loss_streak = 0
        for record in completed:
            if record.result == "LOSS":
                current_streak += 1
                max_loss_streak = max(max_loss_streak, current_streak)
            else:
                current_streak = 0
        return {
            "completed": len(completed),
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / len(completed)) if completed else None,
            "loss_streak": current_streak,
            "max_loss_streak": max_loss_streak,
            "direction": direction,
            "decision_distribution": {
                decision: sum(r.decision == decision for r in self._records)
                for decision in ("EXECUTAR", "BLOQUEAR", "AGUARDAR")
            },
        }
