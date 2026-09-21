from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from core.file_lock import exclusive_file_lock
from core.safe_file import read_regular_utf8

from core.models import Signal
from core.operation_memory import OperationMemory, OperationMemoryRecord


MAX_MEMORY_RECORDS = 10_000
MAX_MEMORY_FILE_BYTES = 4 * 1024 * 1024


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
        records = memory.records()
        if len(records) > MAX_MEMORY_RECORDS:
            raise ValueError("memória excede o limite permitido.")
        payload = [self._serialize(record) for record in records]
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        if len(encoded) > MAX_MEMORY_FILE_BYTES:
            raise ValueError("arquivo de memória excede o limite permitido.")
        with exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock")):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.parent.resolve(strict=True) != self.path.parent.absolute():
                raise OSError("diretório da memória não pode ser symlink")
            if self.path.exists() and (self.path.is_symlink() or not self.path.is_file()):
                raise OSError("arquivo de memória deve ser regular")
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                fd = None
                try:
                    fd = os.open(temporary, flags, 0o600)
                    with os.fdopen(fd, "wb") as handle:
                        fd = None
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, self.path)
                except FileExistsError as exc:
                    raise RuntimeError("arquivo temporário da memória já existe") from exc
                finally:
                    if fd is not None:
                        os.close(fd)
                    try:
                        temporary.unlink()
                    except FileNotFoundError:
                        pass
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:
                    pass

    def load(self) -> OperationMemory:
        memory = OperationMemory()
        with exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock")):
            if not self.path.exists():
                return memory
            try:
                stat = self.path.lstat()
                if self.path.is_symlink() or not self.path.is_file():
                    raise ValueError("arquivo de memória deve ser regular.")
                if stat.st_size > MAX_MEMORY_FILE_BYTES:
                    raise ValueError("arquivo de memória excede o limite permitido.")
                payload = json.loads(read_regular_utf8(self.path, max_bytes=MAX_MEMORY_FILE_BYTES ))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError("arquivo de memória inválido.") from exc
            if not isinstance(payload, list) or len(payload) > MAX_MEMORY_RECORDS:
                raise ValueError("arquivo de memória deve conter uma lista válida dentro do limite.")
            for item in payload:
                memory.append(self._deserialize(item))
            return memory
