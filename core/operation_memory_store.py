from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from core.models import Signal
from core.operation_memory import OperationMemory, OperationMemoryRecord


class OperationMemoryStore:
    """Persists validated OperationMemory records as portable JSON."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)

    @staticmethod
    def _serialize(record: OperationMemoryRecord) -> dict[str, object]:
        return {
            "timestamp": record.timestamp.isoformat(),
            "signal": record.signal.value,
            "score": record.score,
            "decision": record.decision,
            "reason": record.reason,
            "result": record.result,
            "symbol": record.symbol,
            "timeframe": record.timeframe,
            "quality_score": record.quality_score,
            "quality_level": record.quality_level,
            "entry_conditions": list(record.entry_conditions),
        }

    @staticmethod
    def _deserialize(data: object) -> OperationMemoryRecord:
        if not isinstance(data, dict):
            raise ValueError("registro persistido inválido.")
        try:
            conditions = data.get("entry_conditions", [])
            if not isinstance(conditions, list):
                raise ValueError("entry_conditions persistido inválido.")
            return OperationMemoryRecord(
                timestamp=datetime.fromisoformat(str(data["timestamp"])),
                signal=Signal(str(data["signal"])),
                score=data["score"],
                decision=str(data["decision"]),
                reason=str(data["reason"]),
                result=str(data.get("result", "PENDENTE")),
                symbol=data.get("symbol"),
                timeframe=data.get("timeframe"),
                quality_score=data.get("quality_score"),
                quality_level=data.get("quality_level"),
                entry_conditions=tuple(str(item) for item in conditions),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("registro persistido inválido.") from exc

    def save(self, memory: OperationMemory) -> None:
        if not isinstance(memory, OperationMemory):
            raise TypeError("memory deve ser OperationMemory.")
        payload = [self._serialize(record) for record in memory.records()]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load(self) -> OperationMemory:
        memory = OperationMemory()
        if not self.path.exists():
            return memory
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("arquivo de memória inválido.") from exc
        if not isinstance(payload, list):
            raise ValueError("arquivo de memória deve conter uma lista.")
        for item in payload:
            memory.append(self._deserialize(item))
        return memory
