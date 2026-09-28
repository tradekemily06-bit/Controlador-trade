from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from core.decision_snapshot import DecisionSnapshot


class OperationContextStore:
    """Durable request-indexed snapshot captured before DEMO execution."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._lock = Lock()

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("store de contexto operacional inválido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("store de contexto operacional deve ser um objeto.")
        return payload

    def put(self, request_id: str, snapshot: DecisionSnapshot) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id é obrigatório.")
        if not isinstance(snapshot, DecisionSnapshot):
            raise ValueError("snapshot inválido.")
        if snapshot.request_id not in (None, request_id):
            raise ValueError("snapshot.request_id não corresponde ao request_id.")
        if not snapshot.decision_id or not snapshot.cycle_id:
            raise ValueError("snapshot precisa de decision_id e cycle_id.")
        with self._lock:
            payload = self._read()
            current = payload.get(request_id)
            if current is not None and current != snapshot.as_dict():
                raise ValueError("contexto persistido não pode ser substituído.")
            payload[request_id] = snapshot.as_dict()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)

    def get(self, request_id: str) -> DecisionSnapshot | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id é obrigatório.")
        with self._lock:
            raw = self._read().get(request_id)
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("contexto operacional persistido inválido.")
        try:
            return DecisionSnapshot(
                signal=str(raw["signal"]),
                analysis_score=raw["analysis_score"],
                confirmed=raw["confirmed"],
                quality_score=raw["quality_score"],
                quality_level=str(raw["quality_level"]),
                actionable=raw["actionable"],
                decision=str(raw["decision"]),
                decision_reason=str(raw["decision_reason"]),
                market_context=raw.get("market_context"),
                market_direction=raw.get("market_direction"),
                market_score=raw.get("market_score"),
                operational_state_available=raw["operational_state_available"],
                trades_today=raw.get("trades_today"),
                consecutive_losses=raw.get("consecutive_losses"),
                symbol=raw.get("symbol"),
                timeframe=raw.get("timeframe"),
                decision_id=raw.get("decision_id"),
                cycle_id=raw.get("cycle_id"),
                request_id=raw.get("request_id"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("contexto operacional persistido inválido.") from exc
