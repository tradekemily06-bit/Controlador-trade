from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class DailyOperationJournalEntry:
    timestamp: str
    request_id: str
    mode: str
    action: str
    symbol: str
    signal: str
    amount: float
    duration_seconds: int
    status: str
    accepted: bool
    external_id: str | None
    message: str


class DailyOperationJournal:
    """Persistent bookkeeping for day-to-day operations.

    This journal is informational/auditable only. It never authorizes,
    retries, reconciles, or changes an execution.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()
        self._entries: list[DailyOperationJournalEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            entries = []
            for item in raw:
                if isinstance(item, dict):
                    entries.append(DailyOperationJournalEntry(**item))
            self._entries = entries
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # A corrupted journal must not become an execution authority.
            self._entries = []

    def append(
        self,
        *,
        request_id: str,
        mode: str,
        action: str,
        symbol: str,
        signal: str,
        amount: float,
        duration_seconds: int,
        status: str,
        accepted: bool,
        external_id: str | None,
        message: str,
        timestamp: datetime | None = None,
    ) -> DailyOperationJournalEntry:
        entry = DailyOperationJournalEntry(
            timestamp=(timestamp or datetime.now(timezone.utc)).isoformat(),
            request_id=str(request_id),
            mode=str(mode),
            action=str(action),
            symbol=str(symbol),
            signal=str(signal),
            amount=float(amount),
            duration_seconds=int(duration_seconds),
            status=str(status),
            accepted=bool(accepted),
            external_id=None if external_id is None else str(external_id),
            message=str(message),
        )
        with self._lock:
            self._entries.append(entry)
            self._persist()
        return entry

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(
            [asdict(item) for item in self._entries],
            ensure_ascii=False,
            indent=2,
        )
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def entries(self, limit: int = 100) -> tuple[DailyOperationJournalEntry, ...]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        with self._lock:
            return tuple(self._entries[-limit:][::-1])

    def today(self, *, now: datetime | None = None) -> tuple[DailyOperationJournalEntry, ...]:
        current = now or datetime.now(timezone.utc)
        day = current.date()
        with self._lock:
            return tuple(
                entry for entry in reversed(self._entries)
                if datetime.fromisoformat(entry.timestamp).date() == day
            )

    def summary(self) -> dict[str, Any]:
        entries = self.today()
        return {
            "date_utc": datetime.now(timezone.utc).date().isoformat(),
            "total": len(entries),
            "accepted": sum(item.accepted for item in entries),
            "rejected": sum(not item.accepted for item in entries),
            "wins": 0,
            "losses": 0,
            "note": "resultados WIN/LOSS são liquidados em memória de operação; este diário registra o ciclo operacional",
        }
