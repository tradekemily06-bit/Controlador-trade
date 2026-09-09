from __future__ import annotations

import json
from pathlib import Path


class ExecutionLedger:
    """Persists processed execution request IDs for restart-safe idempotency."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._processed: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        if not isinstance(payload, list) or any(
            not isinstance(item, str) or not item.strip() for item in payload
        ):
            raise ValueError("ledger de execução inválido.")
        self._processed = set(payload)

    def contains(self, request_id: str) -> bool:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        return request_id in self._processed

    def record(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        if request_id in self._processed:
            return
        updated = set(self._processed)
        updated.add(request_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(sorted(updated), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._processed = updated

    def records(self) -> tuple[str, ...]:
        return tuple(sorted(self._processed))
