from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .decision_audit import DecisionAudit, DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .durable_json import atomic_write_json, locked_path, read_json
from .kill_switch import KillSwitch, KillSwitchState


class OperationalSafetyStore:
    """Persists validated operational audit, execution audit and kill-switch state."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)

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
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("snapshot persistido inválido.") from exc

    @classmethod
    def _audit_record(cls, data: object) -> DecisionAuditRecord:
        if not isinstance(data, dict):
            raise ValueError("auditoria persistida inválida.")
        try:
            return DecisionAuditRecord(
                timestamp=datetime.fromisoformat(str(data["timestamp"])),
                snapshot=cls._snapshot(data["snapshot"]),
            )
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

    def _read_payload_unlocked(self) -> dict[str, object]:
        if not self.path.exists():
            return {"audit": [], "kill_switch": {}, "execution_audit": []}
        try:
            payload = read_json(self.path, {})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("estado de segurança inválido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("estado de segurança deve ser um objeto.")
        return payload

    @staticmethod
    def _audit_from_payload(payload: dict[str, object]) -> DecisionAudit:
        raw = payload.get("audit", [])
        if not isinstance(raw, list):
            raise ValueError("auditoria persistida inválida.")
        audit = DecisionAudit()
        for item in raw:
            audit.append(OperationalSafetyStore._audit_record(item))
        return audit

    @classmethod
    def _normalize_execution_audit(cls, payload: dict[str, object]) -> list[dict[str, object]]:
        raw = payload.get("execution_audit", [])
        if not isinstance(raw, list):
            raise ValueError("auditoria de execução persistida inválida.")

        normalized = [cls._execution_audit_item(item) for item in raw]
        previous: datetime | None = None
        for item in normalized:
            current = datetime.fromisoformat(str(item["timestamp"]))
            if previous is not None:
                previous_aware = previous.tzinfo is not None and previous.utcoffset() is not None
                current_aware = current.tzinfo is not None and current.utcoffset() is not None
                if previous_aware != current_aware:
                    raise ValueError(
                        "timestamps da auditoria de execução persistida devem usar o mesmo regime de timezone."
                    )
                if current < previous:
                    raise ValueError(
                        "auditoria de execução persistida deve permanecer cronológica."
                    )
            previous = current
        return normalized

    @staticmethod
    def _normalize_kill_switch(data: object) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError("estado do kill switch inválido.")
        state = KillSwitchState(enabled=data.get("enabled", False), reason=data.get("reason"))
        return {"enabled": state.enabled, "reason": state.reason}

    def save(self, audit: DecisionAudit, kill_switch: KillSwitch) -> None:
        if not isinstance(audit, DecisionAudit):
            raise TypeError("audit deve ser DecisionAudit.")
        if not isinstance(kill_switch, KillSwitch):
            raise TypeError("kill_switch deve ser KillSwitch.")
        state = kill_switch.state
        try:
            with locked_path(self.path):
                payload = self._read_payload_unlocked()
                execution_audit = self._normalize_execution_audit(payload)
                # save() must not let an older in-memory audit or disabled
                # kill-switch snapshot erase newer durable safety state.
                incoming = audit.records()
                durable_audit = self._audit_from_payload(payload)
                merged_audit = list(durable_audit.records())
                for record in incoming:
                    if record not in merged_audit:
                        merged_audit.append(record)
                merged_audit.sort(key=lambda item: item.timestamp)
                durable_kill = self._normalize_kill_switch(payload.get("kill_switch", {}))
                # Safety is monotonic for stale snapshots: an already-active
                # durable kill switch can only be explicitly changed through
                # save_kill_switch(), never by a generic stale save().
                if durable_kill["enabled"] and not state.enabled:
                    persisted_kill = durable_kill
                else:
                    persisted_kill = {"enabled": state.enabled, "reason": state.reason}
                payload = {
                    "audit": [self._audit_dict(record) for record in merged_audit],
                    "kill_switch": persisted_kill,
                    "execution_audit": execution_audit,
                }
                atomic_write_json(self.path, payload)
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir o estado de segurança.") from exc

    def append_audit(self, record: DecisionAuditRecord) -> DecisionAuditRecord:
        """Append one audit event to the latest durable snapshot without stale-snapshot overwrite."""
        if not isinstance(record, DecisionAuditRecord):
            raise TypeError("record deve ser DecisionAuditRecord.")
        try:
            with locked_path(self.path):
                payload = self._read_payload_unlocked()
                audit = self._audit_from_payload(payload)
                if record not in audit.records():
                    audit.append(record)
                execution_audit = self._normalize_execution_audit(payload)
                kill_switch = self._normalize_kill_switch(payload.get("kill_switch", {}))
                atomic_write_json(
                    self.path,
                    {
                        "audit": [self._audit_dict(item) for item in audit.records()],
                        "kill_switch": kill_switch,
                        "execution_audit": execution_audit,
                    },
                )
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir a auditoria.") from exc
        return record

    def save_kill_switch(self, kill_switch: KillSwitch) -> None:
        """Persist only the safety switch against the latest durable snapshot."""
        if not isinstance(kill_switch, KillSwitch):
            raise TypeError("kill_switch deve ser KillSwitch.")
        state = kill_switch.state
        try:
            with locked_path(self.path):
                payload = self._read_payload_unlocked()
                audit = self._audit_from_payload(payload)
                execution_audit = self._normalize_execution_audit(payload)
                atomic_write_json(
                    self.path,
                    {
                        "audit": [self._audit_dict(item) for item in audit.records()],
                        "kill_switch": {"enabled": state.enabled, "reason": state.reason},
                        "execution_audit": execution_audit,
                    },
                )
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir o estado do kill switch.") from exc

    def append_execution_audit(self, event: dict[str, object]) -> dict[str, object]:
        """Append one execution-audit event to the latest durable snapshot."""
        normalized = self._execution_audit_item(event)
        try:
            with locked_path(self.path):
                payload = self._read_payload_unlocked()
                audit = self._audit_from_payload(payload)
                kill_switch = self._normalize_kill_switch(payload.get("kill_switch", {}))
                execution_audit = self._normalize_execution_audit(payload)
                if execution_audit:
                    last_timestamp = datetime.fromisoformat(str(execution_audit[-1]["timestamp"]))
                    event_timestamp = datetime.fromisoformat(str(normalized["timestamp"]))
                    last_aware = last_timestamp.tzinfo is not None and last_timestamp.utcoffset() is not None
                    event_aware = event_timestamp.tzinfo is not None and event_timestamp.utcoffset() is not None
                    if last_aware != event_aware:
                        raise ValueError("timestamps da auditoria de execução devem usar o mesmo regime de timezone.")
                    if event_timestamp < last_timestamp:
                        raise ValueError("auditoria de execução deve permanecer cronológica.")
                if normalized not in execution_audit:
                    execution_audit.append(normalized)
                atomic_write_json(
                    self.path,
                    {
                        "audit": [self._audit_dict(record) for record in audit.records()],
                        "kill_switch": kill_switch,
                        "execution_audit": execution_audit,
                    },
                )
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir a auditoria de execução.") from exc
        return normalized

    def save_execution_audit(self, events: tuple[dict[str, object], ...]) -> None:
        if not isinstance(events, tuple):
            raise TypeError("events deve ser tuple.")
        normalized = [self._execution_audit_item(item) for item in events]
        try:
            with locked_path(self.path):
                payload = self._read_payload_unlocked()
                audit = self._audit_from_payload(payload)
                kill_switch = self._normalize_kill_switch(payload.get("kill_switch", {}))
                durable = self._normalize_execution_audit(payload)
                merged = list(durable)
                for event in normalized:
                    if event not in merged:
                        if merged:
                            last_timestamp = datetime.fromisoformat(str(merged[-1]["timestamp"]))
                            event_timestamp = datetime.fromisoformat(str(event["timestamp"]))
                            last_aware = last_timestamp.tzinfo is not None and last_timestamp.utcoffset() is not None
                            event_aware = event_timestamp.tzinfo is not None and event_timestamp.utcoffset() is not None
                            if last_aware != event_aware:
                                raise ValueError("timestamps da auditoria de execução devem usar o mesmo regime de timezone.")
                            if event_timestamp < last_timestamp:
                                raise ValueError("auditoria de execução deve permanecer cronológica.")
                        merged.append(event)
                atomic_write_json(
                    self.path,
                    {
                        "audit": [self._audit_dict(record) for record in audit.records()],
                        "kill_switch": kill_switch,
                        "execution_audit": merged,
                    },
                )
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir a auditoria de execução.") from exc

    @contextmanager
    def kill_switch_execution_window(self):
        """Hold the shared safety-state lock across a REAL side-effect window.

        The caller reads the latest durable kill-switch state while holding the
        same file lock used by save_kill_switch(). This closes the cross-process
        race where one worker could dispatch while another worker activates the
        persistent emergency stop.
        """
        try:
            with locked_path(self.path):
                payload = self._read_payload_unlocked()
                kill_switch_data = self._normalize_kill_switch(payload.get("kill_switch", {}))
                yield KillSwitchState(
                    enabled=kill_switch_data["enabled"],
                    reason=kill_switch_data["reason"],
                )
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível ler o estado persistido do kill switch.") from exc

    def load_execution_audit(self) -> tuple[dict[str, object], ...]:
        try:
            with locked_path(self.path):
                payload = self._read_payload_unlocked()
                return tuple(self._normalize_execution_audit(payload))
        except ValueError:
            raise
        except OSError as exc:
            raise ValueError("estado de segurança inválido.") from exc

    def load(self) -> tuple[DecisionAudit, KillSwitch]:
        audit, kill_switch = DecisionAudit(), KillSwitch()
        try:
            with locked_path(self.path):
                if not self.path.exists():
                    return audit, kill_switch
                payload = self._read_payload_unlocked()
                audit = self._audit_from_payload(payload)
                kill_switch_data = self._normalize_kill_switch(payload.get("kill_switch", {}))
                state = KillSwitchState(enabled=kill_switch_data["enabled"], reason=kill_switch_data["reason"])
                if state.enabled:
                    kill_switch.activate(state.reason or "estado persistido")
                else:
                    kill_switch.deactivate()
                self._normalize_execution_audit(payload)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("estado de segurança inválido.") from exc
        except OSError as exc:
            raise ValueError("estado de segurança inválido.") from exc
        return audit, kill_switch
