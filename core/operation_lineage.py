from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass(frozen=True)
class OperationLineage:
    """Persistent identity chain for one controlled operation."""

    decision_id: str
    cycle_id: str
    request_id: str
    external_id: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("decision_id", "cycle_id", "request_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if self.external_id is not None and (not isinstance(self.external_id, str) or not self.external_id.strip()):
            raise ValueError("external_id inválido.")
        if self.updated_at is not None and not isinstance(self.updated_at, datetime):
            raise ValueError("updated_at inválido.")


class OperationLineageStore:
    """Durable request-indexed lineage; writes are atomic and restart-safe."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, OperationLineage] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            self._records = {}
            for request_id, raw in payload.items():
                if not isinstance(raw, dict):
                    raise ValueError
                record = OperationLineage(
                    decision_id=str(raw["decision_id"]),
                    cycle_id=str(raw["cycle_id"]),
                    request_id=str(raw.get("request_id", request_id)),
                    external_id=raw.get("external_id"),
                    updated_at=datetime.fromisoformat(raw["updated_at"]) if raw.get("updated_at") else None,
                )
                if record.request_id != request_id:
                    raise ValueError("request_id da linhagem não corresponde à chave.")
                self._records[request_id] = record
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("store de linhagem operacional inválido.") from exc

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            request_id: {
                "decision_id": record.decision_id,
                "cycle_id": record.cycle_id,
                "request_id": record.request_id,
                "external_id": record.external_id,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }
            for request_id, record in sorted(self._records.items())
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def put(self, record: OperationLineage) -> None:
        if not isinstance(record, OperationLineage):
            raise ValueError("linhagem inválida.")
        current = self._records.get(record.request_id)
        if current is not None:
            if current.decision_id != record.decision_id or current.cycle_id != record.cycle_id:
                raise ValueError("request_id não pode mudar de decisão/ciclo.")
            if current.external_id is not None and record.external_id != current.external_id:
                raise ValueError("external_id persistido não pode ser substituído.")
        self._records[record.request_id] = record
        self._save()

    def attach_external_id(self, request_id: str, external_id: str, *, updated_at: datetime | None = None) -> OperationLineage:
        current = self.get(request_id)
        if current is None:
            raise ValueError("request_id sem linhagem persistida.")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id é obrigatório.")
        if current.external_id is not None and current.external_id != external_id:
            raise ValueError("external_id conflitante.")
        updated = OperationLineage(current.decision_id, current.cycle_id, current.request_id, external_id, updated_at)
        self.put(updated)
        return updated

    def get(self, request_id: str) -> OperationLineage | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id é obrigatório.")
        self._load()
        return self._records.get(request_id)

    def records(self) -> tuple[OperationLineage, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))
