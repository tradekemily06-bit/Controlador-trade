"""Durable, fail-closed technical incident state shared by execution workers."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from core.file_lock import exclusive_file_lock


MAX_INCIDENT_FILE_BYTES = 64 * 1024
MAX_INCIDENT_ID_LENGTH = 256
MAX_INCIDENT_REASON_LENGTH = 4096


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
            return {"status": "HEALTHY", "incident_id": None, "reason": None, "changed_at": None}
        try:
            stat = self.path.lstat()
        except OSError as exc:
            raise ValueError("estado de incidente técnico inválido") from exc
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("estado de incidente técnico deve ser um arquivo regular")
        if stat.st_size > MAX_INCIDENT_FILE_BYTES:
            raise ValueError("estado de incidente técnico inválido")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("estado de incidente técnico inválido") from exc
        if not isinstance(value, dict) or value.get("status") not in ("HEALTHY", "INCIDENT"):
            raise ValueError("estado de incidente técnico inválido")
        incident_id = value.get("incident_id")
        if incident_id is not None and (not isinstance(incident_id, str) or not incident_id.strip() or len(incident_id.strip()) > MAX_INCIDENT_ID_LENGTH):
            raise ValueError("incident_id de incidente técnico inválido")
        reason = value.get("reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > MAX_INCIDENT_REASON_LENGTH):
            raise ValueError("reason de incidente técnico inválido")
        changed_at = value.get("changed_at")
        if changed_at is not None and (not isinstance(changed_at, str) or datetime.fromisoformat(changed_at).tzinfo is None):
            raise ValueError("timestamp de incidente técnico inválido")
        if value.get("status") == "INCIDENT":
            if incident_id is None or reason is None or changed_at is None:
                raise ValueError("incidente técnico ativo está incompleto")
            return value
        if value.get("status") == "HEALTHY" and incident_id is not None:
            raise ValueError("incidente resolvido não pode manter incident_id ativo")
        return value

    def _write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > MAX_INCIDENT_FILE_BYTES:
            raise ValueError("estado de incidente técnico excede o limite permitido")
        try:
            temporary.write_bytes(encoded)
            with temporary.open("r+b") as handle:
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            try:
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
        finally:
            try:
                if temporary.exists(): temporary.unlink()
            except OSError: pass

    def status(self) -> dict[str, object]:
        with self._lock_local, self._file_lock():
            return self._read()

    def open(self, incident_id: str, reason: str, *, now: datetime | None = None) -> dict[str, object]:
        if not isinstance(incident_id, str) or not incident_id.strip(): raise ValueError("incident_id é obrigatório")
        if not isinstance(reason, str) or not reason.strip(): raise ValueError("reason é obrigatório")
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None: raise ValueError("timestamp deve conter timezone")
        normalized_id = incident_id.strip()
        normalized_reason = reason.strip()
        if len(normalized_id) > MAX_INCIDENT_ID_LENGTH or len(normalized_reason) > MAX_INCIDENT_REASON_LENGTH:
            raise ValueError("estado de incidente técnico excede o limite permitido")
        payload = {"status":"INCIDENT","incident_id":normalized_id,"reason":normalized_reason,"changed_at":timestamp.astimezone(timezone.utc).isoformat()}
        with self._lock_local, self._file_lock():
            current = self._read()
            if current.get("status") == "INCIDENT" and current.get("incident_id") != normalized_id:
                raise ValueError("já existe outro incidente técnico ativo")
            self._write(payload)
        return payload

    def resolve(self, incident_id: str, *, now: datetime | None = None) -> dict[str, object]:
        if not isinstance(incident_id, str) or not incident_id.strip(): raise ValueError("incident_id é obrigatório")
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None: raise ValueError("timestamp deve conter timezone")
        with self._lock_local, self._file_lock():
            current = self._read()
            if current.get("status") != "INCIDENT": raise ValueError("nenhum incidente técnico ativo")
            persisted_id = current.get("incident_id")
            if persisted_id != incident_id.strip(): raise ValueError("incident_id não corresponde ao incidente técnico ativo")
            payload = {"status":"HEALTHY","incident_id":None,"reason":None,"changed_at":timestamp.astimezone(timezone.utc).isoformat()}
            self._write(payload)
        return payload
