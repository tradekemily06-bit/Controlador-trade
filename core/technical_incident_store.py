"""Durable, fail-closed technical incident state shared by execution workers."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from core.file_lock import exclusive_file_lock


class TechnicalIncidentStore:
    """Atomic cross-process store for the global execution stop state."""
    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório")
        self.path = Path(path)
        self._lock_local = RLock()

    def _file_lock(self):
        return exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock"))

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"status": "HEALTHY", "reason": None, "changed_at": None}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("estado de incidente técnico inválido") from exc
        if not isinstance(value, dict) or value.get("status") not in ("HEALTHY", "INCIDENT"):
            raise ValueError("estado de incidente técnico inválido")
        reason = value.get("reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError("reason de incidente técnico inválido")
        changed_at = value.get("changed_at")
        if changed_at is not None:
            if not isinstance(changed_at, str) or datetime.fromisoformat(changed_at).tzinfo is None:
                raise ValueError("timestamp de incidente técnico inválido")
        return value

    def _write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            with temporary.open("r+b") as handle:
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                if temporary.exists(): temporary.unlink()
            except OSError:
                pass

    def status(self) -> dict[str, object]:
        with self._lock_local, self._file_lock():
            return self._read()

    def open(self, reason: str, *, now: datetime | None = None) -> dict[str, object]:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason é obrigatório")
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("timestamp deve conter timezone")
        payload = {"status": "INCIDENT", "reason": reason.strip(), "changed_at": timestamp.astimezone(timezone.utc).isoformat()}
        with self._lock_local, self._file_lock():
            self._read(); self._write(payload)
        return payload

    def resolve(self, *, now: datetime | None = None) -> dict[str, object]:
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("timestamp deve conter timezone")
        payload = {"status": "HEALTHY", "reason": None, "changed_at": timestamp.astimezone(timezone.utc).isoformat()}
        with self._lock_local, self._file_lock():
            self._read(); self._write(payload)
        return payload
