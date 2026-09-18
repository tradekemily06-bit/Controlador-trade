from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.models import Signal
from core.operation_memory import OperationMemory, OperationMemoryRecord
from core.durable_json import atomic_write_json, locked_path


class OperationMemoryStore:
    """Persists validated OperationMemory records as portable JSON."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._last_loaded_records: tuple[OperationMemoryRecord, ...] | None = None

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

    def _load_unlocked(self) -> OperationMemory:
        memory = OperationMemory()
        if not self.path.exists():
            return memory
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("arquivo de memória deve conter uma lista.")
            for item in payload:
                memory.append(self._deserialize(item))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("arquivo de memória inválido.") from exc
        return memory

    def _write_unlocked(self, memory: OperationMemory) -> None:
        payload = [self._serialize(record) for record in memory.records()]
        atomic_write_json(self.path, payload)

    @staticmethod
    def _identity(record: OperationMemoryRecord) -> tuple[object, ...]:
        return (
            record.timestamp,
            record.signal,
            record.score,
            record.decision,
            record.reason,
            record.symbol,
            record.timeframe,
            record.quality_score,
            record.quality_level,
            record.entry_conditions,
        )

    def save(self, memory: OperationMemory) -> None:
        if not isinstance(memory, OperationMemory):
            raise TypeError("memory deve ser OperationMemory.")
        with locked_path(self.path):
            durable = self._load_unlocked()
            durable_records = durable.records()
            incoming = memory.records()
            if self._last_loaded_records is None and durable_records:
                raise ValueError("snapshot de memória obsoleto; sobrescrita destrutiva recusada.")
            if self._last_loaded_records is not None and durable_records != self._last_loaded_records:
                raise ValueError("snapshot de memória obsoleto; sobrescrita destrutiva recusada.")
            if not durable_records:
                self._write_unlocked(memory)
                self._last_loaded_records = incoming
                return

            # Preserve the legacy full-snapshot API while making stale writes
            # non-destructive. New records may extend the durable snapshot;
            # an existing operation may only move from PENDENTE to one final
            # result. Competing replacements are rejected instead of guessed.
            durable_by_identity = {self._identity(record): record for record in durable_records}
            merged = list(durable_records)
            positions = {self._identity(record): index for index, record in enumerate(merged)}
            for record in incoming:
                identity = self._identity(record)
                existing = durable_by_identity.get(identity)
                if existing is None:
                    positions[identity] = len(merged)
                    merged.append(record)
                    durable_by_identity[identity] = record
                    continue
                if existing == record:
                    continue
                if existing.result == "PENDENTE" and record.result != "PENDENTE":
                    merged[positions[identity]] = record
                    durable_by_identity[identity] = record
                    continue
                raise ValueError("snapshot de memória obsoleto; sobrescrita destrutiva recusada.")

            merged.sort(key=lambda item: item.timestamp)
            rebuilt = OperationMemory()
            for record in merged:
                rebuilt.append(record)
            self._write_unlocked(rebuilt)
            self._last_loaded_records = rebuilt.records()

    def append(self, record: OperationMemoryRecord) -> OperationMemoryRecord:
        """Atomically append to the latest durable snapshot, avoiding stale-snapshot loss."""
        if not isinstance(record, OperationMemoryRecord):
            raise TypeError("record deve ser OperationMemoryRecord.")
        with locked_path(self.path):
            memory = self._load_unlocked()
            memory.append(record)
            self._write_unlocked(memory)
            self._last_loaded_records = memory.records()
        return record

    def settle(self, record: OperationMemoryRecord, result: str) -> OperationMemoryRecord:
        """Atomically settle against the latest durable snapshot."""
        if not isinstance(record, OperationMemoryRecord):
            raise TypeError("record deve ser OperationMemoryRecord.")
        with locked_path(self.path):
            memory = self._load_unlocked()
            updated = memory.settle(record, result)
            self._write_unlocked(memory)
            self._last_loaded_records = memory.records()
        return updated

    def load(self) -> OperationMemory:
        try:
            with locked_path(self.path):
                memory = self._load_unlocked()
                self._last_loaded_records = memory.records()
                return memory
        except ValueError:
            raise
        except OSError as exc:
            raise ValueError("arquivo de memória inválido.") from exc
