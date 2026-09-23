from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime


class ExecutionLifecycleState(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionLifecycleRecord:
    request_id: str
    state: ExecutionLifecycleState
    updated_at: datetime
    message: str = ""
    decision_id: str | None = None
    symbol: str | None = None
    signal: str | None = None
    amount: float | None = None
    mode: str | None = None
    external_id: str | None = None


class ExecutionLifecycleStore:
    """Durable execution state; UNKNOWN is terminal until explicitly reconciled."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError
            for item in payload:
                if not isinstance(item, dict):
                    raise ValueError
                record = ExecutionLifecycleRecord(
                    request_id=item["request_id"],
                    state=ExecutionLifecycleState(item["state"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                    message=item.get("message", ""),
                    decision_id=item.get("decision_id"), symbol=item.get("symbol"),
                    signal=item.get("signal"), amount=item.get("amount"), mode=item.get("mode"),
                    external_id=item.get("external_id"),
                )
                self._validate(record)
                self._records[record.request_id] = record
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(record.updated_at, datetime):
            raise ValueError("timestamp inválido.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")
        for value, name in ((record.decision_id, "decision_id"), (record.symbol, "symbol"), (record.signal, "signal"), (record.mode, "mode"), (record.external_id, "external_id")):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} inválido.")
        if record.amount is not None and (isinstance(record.amount, bool) or not isinstance(record.amount, (int, float))):
            raise ValueError("amount inválido.")

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)
        previous = self._records.get(record.request_id)
        if previous is not None and previous.state is ExecutionLifecycleState.UNKNOWN and record.state is not ExecutionLifecycleState.UNKNOWN:
            raise ValueError("execução UNKNOWN requer reconciliação explícita.")
        self._records[record.request_id] = record
        self._save()

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        return self._records.get(request_id)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        current = self.get(request_id)
        if current is None:
            raise ValueError("execução não encontrada.")
        record = ExecutionLifecycleRecord(request_id, state, updated_at, message, decision_id=current.decision_id, symbol=current.symbol, signal=current.signal, amount=current.amount, mode=current.mode, external_id=current.external_id)
        self._validate(record)
        self._records[request_id] = record
        self._save()
        return record

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([
                {"request_id": r.request_id, "state": r.state.value, "updated_at": r.updated_at.isoformat(), "message": r.message, "decision_id": r.decision_id, "symbol": r.symbol, "signal": r.signal, "amount": r.amount, "mode": r.mode, "external_id": r.external_id}
                for r in self.records()
            ], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
