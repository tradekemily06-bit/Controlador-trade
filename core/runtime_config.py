from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from execution.ports import ExecutionMode


@dataclass(frozen=True)
class RuntimeConfig:
    """Validated immutable configuration for one trading runtime session."""

    symbol: str
    timeframe: str
    amount: float
    duration_seconds: int
    mode: ExecutionMode = ExecutionMode.DEMO
    data_path: Path | None = None
    memory_path: Path | None = None
    safety_path: Path | None = None
    ledger_path: Path | None = None
    lifecycle_path: Path | None = None
    checkpoint_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol é obrigatório.")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe é obrigatório.")
        if not isinstance(self.amount, (int, float)) or isinstance(self.amount, bool) or not math.isfinite(float(self.amount)) or self.amount <= 0:
            raise ValueError("amount deve ser um número finito positivo.")
        if not isinstance(self.duration_seconds, int) or isinstance(self.duration_seconds, bool) or self.duration_seconds <= 0:
            raise ValueError("duration_seconds deve ser um inteiro positivo.")
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("modo de execução inválido.")
        if self.mode is ExecutionMode.REAL:
            raise ValueError("execução REAL permanece bloqueada nesta etapa.")
        for name in ("data_path", "memory_path", "safety_path", "ledger_path", "lifecycle_path", "checkpoint_path"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Path):
                object.__setattr__(self, name, Path(value))

    def paths(self) -> tuple[Path, ...]:
        return tuple(
            path for path in (
                self.data_path,
                self.memory_path,
                self.safety_path,
                self.ledger_path,
                self.lifecycle_path,
                self.checkpoint_path,
            )
            if path is not None
        )
