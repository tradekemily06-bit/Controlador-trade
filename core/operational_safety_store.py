from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .decision_audit import DecisionAudit, DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .file_lock import exclusive_file_lock
from .kill_switch import KillSwitch, KillSwitchState


MAX_SAFETY_FILE_BYTES = 4 * 1024 * 1024
MAX_SAFETY_AUDIT_RECORDS = 10_000
MAX_SAFETY_EXECUTION_AUDIT_RECORDS = 10_000
MAX_SAFETY_IDENTIFIER_LENGTH = 256
MAX_SAFETY_MESSAGE_LENGTH = 4_096


class OperationalSafetyStore:
    """Persists validated operational audit and kill-switch state atomically."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)

    def _lock(self):
        return exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock"))

    @staticmethod
    def _snapshot(data: object) -> DecisionSnapshot:
        if not isinstance(data, dict):
            raise ValueError("snapshot persistido inválido.")
        try:
            return DecisionSnapshot(
                signal=str(data["signal"]), analysis_score=data["analysis_score"], confirmed=data["confirmed"],
                quality_score=data["quality_score"], quality_level=str(data["quality_level"]), actionable=data["actionable"],
                decision=str(data["decision"]), decision_reason=str(data["decision_reason"]),
                market_context=data.get("market_context"), market_direction=data.get("market_direction"),
                market_score=data.get("market_score"), operational_state_available=data["operational_state_available"],
                trades_today=data.get("trades_today"), consecutive_losses=data.get("consecutive_losses"),
                symbol=data.get("symbol"), timeframe=data.get("timeframe"),
                risk_state_identity=data.get("risk_state_identity"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("snapshot persistido inválido.") from exc

    @classmethod
    def _audit_record(cls, data: object) -> DecisionAuditRecord:
        if not isinstance(data, dict):
            raise ValueError("auditoria persistida inválida.")
        try:
            return DecisionAuditRecord(timestamp=datetime.fromisoformat(str(data["timestamp"])), snapshot=cls._snapshot(data["snapshot"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("auditoria persistida inválida.") from exc

    @staticmethod
    def _audit_dict(record: DecisionAuditRecord) -> dict[str, object]:
        return {"timestamp": record.timestamp.isoformat(), "snapshot": record.snapshot.as_dict()}

    @staticmethod
    def _execution_audit_item(data: object) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError("auditoria de execução persistida inválida.")
        request_id = data.get("request_id")
        state = data.get("state")
        timestamp = data.get("timestamp")
        message = data.get("message")
        valid_states = {"PENDING", "ACCEPTED", "REJECTED", "UNKNOWN"}
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id da auditoria de execução é obrigatório.")
        if not isinstance(state, str) or state not in valid_states:
            raise ValueError("estado da auditoria de execução inválido.")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise ValueError("timestamp da auditoria de execução é obrigatório.")
        try:
            datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValueError("timestamp da auditoria de execução inválido.") from exc
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message da auditoria de execução é obrigatório.")
        return {"request_id": request_id, "state": state, "timestamp": timestamp, "message": message}

    def _read_payload(self) -> dict[str, object]:
        if not self.path.exists():
            return {"audit": [], "kill_switch": {}, "execution_audit": []}
        try:
            stat = self.path.lstat()
            if not self.path.is_file() or self.path.is_symlink():
                raise ValueError("estado de segurança deve ser um arquivo regular.")
            if stat.st_size > MAX_SAFETY_FILE_BYTES:
                raise ValueError("estado de segurança excede o limite permitido.")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("estado de segurança inválido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("estado de segurança deve ser um objeto.")
        audit_items = payload.get("audit", [])
        execution_items = payload.get("execution_audit", [])
        if not isinstance(audit_items, list) or len(audit_items) > MAX_SAFETY_AUDIT_RECORDS:
            raise ValueError("estado de segurança inválido.")
        if not isinstance(execution_items, list) or len(execution_items) > MAX_SAFETY_EXECUTION_AUDIT_RECORDS:
            raise ValueError("estado de segurança inválido.")
        return payload

    def _write_payload(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_SAFETY_FILE_BYTES:
            raise ValueError("estado de segurança excede o limite permitido.")
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_bytes(encoded)
            with temporary.open("r+b") as handle:
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            try:
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
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

    @classmethod
    def _merge_audit_records(cls, persisted: object, current: tuple[DecisionAuditRecord, ...]) -> list[dict[str, object]]:
        if not isinstance(persisted, list):
            raise ValueError("auditoria persistida inválida.")
        merged: dict[str, dict[str, object]] = {}
        for item in persisted:
            record = cls._audit_record(item)
            normalized = cls._audit_dict(record)
            merged[json.dumps(normalized, ensure_ascii=False, sort_keys=True)] = normalized
        for record in current:
            normalized = cls._audit_dict(record)
            merged[json.dumps(normalized, ensure_ascii=False, sort_keys=True)] = normalized
        records = list(merged.values())
        records.sort(key=lambda item: str(item["timestamp"]))
        return records

    @classmethod
    def _merge_execution_audit(cls, persisted: object, current: list[dict[str, object]]) -> list[dict[str, object]]:
        if not isinstance(persisted, list):
            raise ValueError("auditoria de execução persistida inválida.")
        merged: dict[tuple[str, str, str, str], dict[str, object]] = {}
        for item in persisted:
            normalized = cls._execution_audit_item(item)
            key = (normalized["request_id"], normalized["state"], normalized["timestamp"], normalized["message"])
            merged[key] = normalized
        for item in current:
            normalized = cls._execution_audit_item(item)
            key = (normalized["request_id"], normalized["state"], normalized["timestamp"], normalized["message"])
            merged[key] = normalized
        records = list(merged.values())
        records.sort(key=lambda item: str(item["timestamp"]))
        return records

    def load_execution_audit(self) -> tuple[dict[str, object], ...]:
        with self._lock():
            payload = self._read_payload()
            persisted = payload.get("execution_audit", [])
            if not isinstance(persisted, list):
                raise ValueError("auditoria de execução persistida inválida.")
            return tuple(self._execution_audit_item(item) for item in persisted)

    def save_execution_audit(self, events: tuple[dict[str, object], ...] | list[dict[str, object]]) -> None:
        if not isinstance(events, (tuple, list)):
            raise TypeError("events deve ser lista ou tupla.")
        with self._lock():
            payload = self._read_payload()
            merged = self._merge_execution_audit(payload.get("execution_audit", []), list(events))
            payload["execution_audit"] = merged
            self._write_payload(payload)

    def replace_with_fail_closed_state(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason é obrigatório.")
        with self._lock():
            self._write_payload({"audit": [], "kill_switch": {"enabled": True, "reason": reason}, "execution_audit": []})

    def save(self, audit: DecisionAudit, kill_switch: KillSwitch | KillSwitchState) -> None:
        if not isinstance(audit, DecisionAudit):
            raise TypeError("audit deve ser DecisionAudit.")
        if not isinstance(kill_switch, (KillSwitch, KillSwitchState)):
            raise TypeError("kill_switch deve ser KillSwitch ou KillSwitchState.")
        state = kill_switch.state
        with self._lock():
            payload = self._read_payload()
            normalized_execution = [self._execution_audit_item(item) for item in payload.get("execution_audit", [])]
            merged_audit = self._merge_audit_records(payload.get("audit", []), audit.records())
            persisted_state = payload.get("kill_switch", {})
            if not isinstance(persisted_state, dict):
                raise ValueError("estado do kill switch inválido.")
            safe_state = {
                "enabled": bool(persisted_state.get("enabled", False)) or state.enabled,
                "reason": state.reason if state.enabled else persisted_state.get("reason"),
            }
            self._write_payload({"audit": merged_audit, "kill_switch": safe_state, "execution_audit": normalized_execution})

    def set_kill_switch(self, *, enabled: bool, reason: str | None = None) -> KillSwitchState:
        if not isinstance(enabled, bool):
            raise TypeError("enabled deve ser bool.")
        if enabled and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError("reason é obrigatório ao ativar o kill switch.")
        with self._lock():
            payload = self._read_payload()
            persisted = payload.get("kill_switch", {})
            if not isinstance(persisted, dict):
                raise ValueError("estado do kill switch inválido.")
            state = KillSwitchState(enabled=enabled, reason=reason if enabled else None)
            payload["kill_switch"] = {"enabled": state.enabled, "reason": state.reason}
            self._write_payload(payload)
            return state

    def load(self) -> tuple[DecisionAudit, KillSwitchState]:
        with self._lock():
            payload = self._read_payload()
            audit = DecisionAudit()
            for item in payload.get("audit", []):
                audit.append(self._audit_record(item))
            persisted = payload.get("kill_switch", {})
            if not isinstance(persisted, dict):
                raise ValueError("estado do kill switch inválido.")
            return audit, KillSwitchState(enabled=bool(persisted.get("enabled", False)), reason=persisted.get("reason"))
