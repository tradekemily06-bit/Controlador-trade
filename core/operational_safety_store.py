from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .decision_audit import DecisionAudit, DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .kill_switch import KillSwitch, KillSwitchState


class OperationalSafetyStore:
    """Persists the validated audit trail and kill-switch state."""

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

    def save(self, audit: DecisionAudit, kill_switch: KillSwitch) -> None:
        if not isinstance(audit, DecisionAudit):
            raise TypeError("audit deve ser DecisionAudit.")
        if not isinstance(kill_switch, KillSwitch):
            raise TypeError("kill_switch deve ser KillSwitch.")
        state = kill_switch.state
        payload = {
            "audit": [self._audit_dict(record) for record in audit.records()],
            "kill_switch": {"enabled": state.enabled, "reason": state.reason},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def load(self) -> tuple[DecisionAudit, KillSwitch]:
        audit, kill_switch = DecisionAudit(), KillSwitch()
        if not self.path.exists():
            return audit, kill_switch
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("estado de segurança inválido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("estado de segurança deve ser um objeto.")
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
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("estado de segurança inválido.") from exc
        return audit, kill_switch
