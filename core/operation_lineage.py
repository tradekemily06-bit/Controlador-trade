from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from threading import RLock\n\nfrom core.cross_process_file_lock import cross_process_file_lock


@dataclass(frozen=True)
class OperationLineage:
    """Persistent identity chain for one controlled operation."""

    decision_id: str
    cycle_id: str
    request_id: str
    external_id: str | None = None
    external_container_id: str | None = None
    external_close_id: str | None = None
    external_close_ids: tuple[str, ...] = ()
    external_result_ids: tuple[str, ...] = ()
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("decision_id", "cycle_id", "request_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        for name in ("external_id", "external_container_id", "external_close_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} inválido.")
        if not isinstance(self.external_close_ids, tuple) or any(not isinstance(value, str) or not value.strip() for value in self.external_close_ids):
            raise ValueError("external_close_ids inválido.")
        if len(set(self.external_close_ids)) != len(self.external_close_ids):
            raise ValueError("external_close_ids não podem conter duplicados.")
        if self.external_close_id is not None and self.external_close_id not in self.external_close_ids:
            raise ValueError("external_close_id deve pertencer a external_close_ids.")
        if not isinstance(self.external_result_ids, tuple) or any(
            not isinstance(value, str) or not value.strip() for value in self.external_result_ids
        ):
            raise ValueError("external_result_ids inválido.")
        if len(set(self.external_result_ids)) != len(self.external_result_ids):
            raise ValueError("external_result_ids não podem conter duplicados.")
        if self.updated_at is not None and not isinstance(self.updated_at, datetime):
            raise ValueError("updated_at inválido.")


class OperationLineageStore:
    """Durable request-indexed lineage; writes are atomic and restart-safe."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, OperationLineage] = {}
        self._lock = RLock()
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
                raw_deals = raw.get("external_result_ids", ())
                if not isinstance(raw_deals, (list, tuple)):
                    raise ValueError
                record = OperationLineage(
                    decision_id=str(raw["decision_id"]),
                    cycle_id=str(raw["cycle_id"]),
                    request_id=str(raw.get("request_id", request_id)),
                    external_id=raw.get("external_id"),
                    external_container_id=raw.get("external_container_id"),
                    external_close_id=raw.get("external_close_id"),
                    external_close_ids=tuple(str(value) for value in raw.get("external_close_ids", ([raw.get("external_close_id")] if raw.get("external_close_id") else []))),
                    external_result_ids=tuple(str(value) for value in raw_deals),
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
                "external_container_id": record.external_container_id,
                "external_close_id": record.external_close_id,
                "external_close_ids": list(record.external_close_ids),
                "external_result_ids": list(record.external_result_ids),
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }
            for request_id, record in sorted(self._records.items())
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def put(self, record: OperationLineage) -> None:
        if not isinstance(record, OperationLineage):
            raise ValueError("linhagem inválida.")
        with self._lock:
            self._load()
            current = self._records.get(record.request_id)
            if current is not None:
                if current.decision_id != record.decision_id or current.cycle_id != record.cycle_id:
                    raise ValueError("request_id não pode mudar de decisão/ciclo.")
                if current.external_id is not None and record.external_id != current.external_id:
                    raise ValueError("external_id persistido não pode ser substituído.")
                if current.external_container_id is not None and record.external_container_id != current.external_container_id:
                    raise ValueError("external_container_id persistido não pode ser substituído.")
                if current.external_close_id is not None and record.external_close_id != current.external_close_id:
                    raise ValueError("external_close_id persistido não pode ser substituído.")
                if current.external_result_ids:
                    current_ids = set(current.external_result_ids)
                    incoming_ids = set(record.external_result_ids)
                    if not current_ids.issubset(incoming_ids):
                        raise ValueError("external_result_ids persistidos não podem desaparecer.")
            self._records[record.request_id] = record
            self._save()

    def attach_external_id(self, request_id: str, external_id: str, *, updated_at: datetime | None = None) -> OperationLineage:
        with self._lock:
            current = self.get(request_id)
            if current is None:
                raise ValueError("request_id sem linhagem persistida.")
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id é obrigatório.")
            if current.external_id is not None and current.external_id != external_id:
                raise ValueError("external_id conflitante.")
            updated = OperationLineage(
                current.decision_id, current.cycle_id, current.request_id,
                external_id, current.external_container_id, current.external_close_id,
                current.external_close_ids, current.external_result_ids, updated_at,
            )
            self.put(updated)
            return updated

    def attach_external_container_id(self, request_id: str, external_container_id: str, *, updated_at: datetime | None = None) -> OperationLineage:
        with self._lock:
            current = self.get(request_id)
            if current is None:
                raise ValueError("request_id sem linhagem persistida.")
            if not isinstance(external_container_id, str) or not external_container_id.strip():
                raise ValueError("external_container_id é obrigatório.")
            if current.external_container_id is not None and current.external_container_id != external_container_id:
                raise ValueError("external_container_id conflitante.")
            updated = OperationLineage(
                decision_id=current.decision_id,
                cycle_id=current.cycle_id,
                request_id=current.request_id,
                external_id=current.external_id,
                external_container_id=external_container_id,
                external_close_id=current.external_close_id,
                external_close_ids=current.external_close_ids,
                external_result_ids=current.external_result_ids,
                updated_at=updated_at,
            )
            self.put(updated)
            return updated

    def attach_external_close_id(self, request_id: str, external_close_id: str, *, updated_at: datetime | None = None) -> OperationLineage:
        with self._lock:
            current = self.get(request_id)
            if current is None:
                raise ValueError("request_id sem linhagem persistida.")
            if not isinstance(external_close_id, str) or not external_close_id.strip():
                raise ValueError("external_close_id é obrigatório.")
            updated = OperationLineage(
                current.decision_id, current.cycle_id, current.request_id,
                current.external_id, current.external_container_id, current.external_close_id or external_close_id,
                tuple(dict.fromkeys((*current.external_close_ids, external_close_id))), current.external_result_ids, updated_at,
            )
            self.put(updated)
            return updated

    def attach_external_result_ids(self, request_id: str, external_result_ids: tuple[str, ...], *, updated_at: datetime | None = None) -> OperationLineage:
        with self._lock:
            current = self.get(request_id)
            if current is None:
                raise ValueError("request_id sem linhagem persistida.")
            if not isinstance(external_result_ids, tuple) or not external_result_ids or any(
                not isinstance(value, str) or not value.strip() for value in external_result_ids
            ):
                raise ValueError("external_result_ids são obrigatórios.")
            normalized = tuple(dict.fromkeys(external_result_ids))
            if current.external_result_ids:
                current_ids = set(current.external_result_ids)
                incoming_ids = set(normalized)
                # External history may become complete after the first observation.
                # Existing IDs are immutable evidence; newly discovered IDs may be
                # appended, but the persisted identity can never be replaced.
                if not current_ids.issubset(incoming_ids):
                    raise ValueError("external_result_ids conflitantes: IDs persistidos desapareceram.")
                normalized = tuple(dict.fromkeys((*current.external_result_ids, *normalized)))
            updated = OperationLineage(
                current.decision_id, current.cycle_id, current.request_id,
                current.external_id, current.external_container_id, current.external_close_id,
                current.external_close_ids, normalized, updated_at,
            )
            self.put(updated)
            return updated

    def get(self, request_id: str) -> OperationLineage | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id é obrigatório.")
        with self._lock:
            self._load()
            return self._records.get(request_id)

    def records(self) -> tuple[OperationLineage, ...]:
        with self._lock:
            self._load()
            return tuple(self._records[key] for key in sorted(self._records))
