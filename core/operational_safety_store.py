from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .decision_audit import DecisionAudit, DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .kill_switch import KillSwitch, KillSwitchState


class OperationalSafetyStore:
    """Persists the validated operational audit, execution audit and kill-switch state."""

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
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id da auditoria de execução é obrigatório.")
        if not isinstance(state, str) or not state.strip():
            raise ValueError("estado da auditoria de execução é obrigatório.")
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
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("estado de segurança inválido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("estado de segurança deve ser um objeto.")
        return payload

    def save(self, audit: DecisionAudit, kill_switch: KillSwitch) -> None:
        if not isinstance(audit, DecisionAudit):
            raise TypeError("audit deve ser DecisionAudit.")
        if not isinstance(kill_switch, KillSwitch):
            raise TypeError("kill_switch deve ser KillSwitch.")
        state = kill_switch.state
        payload = self._read_payload()
        execution_audit = payload.get("execution_audit", [])
        if not isinstance(execution_audit, list):
            raise ValueError("auditoria de execução persistida inválida.")
        execution_audit = [self._execution_audit_item(item) for item in execution_audit]
        payload = {
            "audit": [self._audit_dict(record) for record in audit.records()],
            "kill_switch": {"enabled": state.enabled, "reason": state.reason},
            "execution_audit": execution_audit,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def save_execution_audit(self, events: tuple[dict[str, object], ...]) -> None:
        if not isinstance(events, tuple):
            raise TypeError("events deve ser tuple.")
        normalized = [self._execution_audit_item(item) for item in events]
        payload = self._read_payload()
        audit = payload.get("audit", [])
        kill_switch = payload.get("kill_switch", {})
        if not isinstance(audit, list) or not isinstance(kill_switch, dict):
            raise ValueError("estado de segurança inválido.")
        payload = {"audit": audit, "kill_switch": kill_switch, "execution_audit": normalized}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def load_execution_audit(self) -> tuple[dict[str, object], ...]:
        payload = self._read_payload()
        raw = payload.get("execution_audit", [])
        if not isinstance(raw, list):
            raise ValueError("auditoria de execução persistida inválida.")
        return tuple(self._execution_audit_item(item) for item in raw)

    def load(self) -> tuple[DecisionAudit, KillSwitch]:
        audit, kill_switch = DecisionAudit(), KillSwitch()
        if not self.path.exists():
            return audit, kill_switch
        payload = self._read_payload()
        try:
            audit_payload = payload.get("audit", [])
            if not isinstance(audit_payload, list):
                raise ValueError("auditoria persistida inválida.")
            for item in audit_payload:
                audit.append(self._audit_record(item))
            raw_state = payload.get("kill_switch", {})
            if not isinstance(raw_state, dict):
                raise ValueError("estado do kill switch inválido.")
            state = KillSwitchState(enabled=raw_state.get("enabled", False), reason=raw_state.get("reason"))
            if state.enabled:
                kill_switch.activate(state.reason or "estado persistido")
            else:
                kill_switch.deactivate()
            raw_execution_audit = payload.get("execution_audit", [])
            if not isinstance(raw_execution_audit, list):
                raise ValueError("auditoria de execução persistida inválida.")
            for item in raw_execution_audit:
                self._execution_audit_item(item)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("estado de segurança inválido.") from exc
        return audit, kill_switch
