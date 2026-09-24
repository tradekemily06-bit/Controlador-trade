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
    decision_id: str | None = None
    timeframe: str | None = None
    score: float | None = None
    reason: str | None = None
    market_timestamp: str | None = None
    outcome: str | None = None


class DailyOperationJournal:
    """Persistent bookkeeping for day-to-day operations.

    This journal is informational/auditable only. It never authorizes,
    retries, reconciles, or changes an execution.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()
        self._entries: list[DailyOperationJournalEntry] = []
        self._load_error: str | None = None
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
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            # Never overwrite potentially recoverable history automatically.
            self._entries = []
            self._load_error = f"{type(exc).__name__}: {exc}"

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
        decision_id: str | None = None,
        timeframe: str | None = None,
        score: float | None = None,
        reason: str | None = None,
        market_timestamp: str | None = None,
        outcome: str | None = None,
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
            decision_id=None if decision_id is None else str(decision_id),
            timeframe=None if timeframe is None else str(timeframe),
            score=None if score is None else float(score),
            reason=None if reason is None else str(reason),
            market_timestamp=None if market_timestamp is None else str(market_timestamp),
            outcome=None if outcome is None else str(outcome),
        )
        with self._lock:
            if self._load_error is not None:
                raise OSError("diário automático indisponível; histórico existente requer inspeção manual")
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

    def has_market_decision(self, *, symbol: str, timeframe: str, market_timestamp: str) -> bool:
        """Return whether this closed candle was already processed across restarts."""
        if not isinstance(symbol, str) or not symbol.strip() or not isinstance(timeframe, str) or not timeframe.strip() or not isinstance(market_timestamp, str) or not market_timestamp.strip():
            raise ValueError("identidade de candle inválida")
        with self._lock:
            return any(
                entry.decision_id is not None
                and entry.symbol == symbol.strip()
                and entry.timeframe == timeframe.strip()
                and entry.market_timestamp == market_timestamp.strip()
                for entry in self._entries
            )

    def record_outcome(self, *, decision_id: str, outcome: str) -> int:
        """Attach a terminal outcome to journal entries for the decision, without execution authority."""
        if outcome not in {"WIN", "LOSS", "DRAW", "OPEN", "VOID"}:
            raise ValueError("outcome inválido")
        changed = 0
        with self._lock:
            for index, entry in enumerate(self._entries):
                if entry.decision_id == decision_id:
                    self._entries[index] = DailyOperationJournalEntry(
                        **{**asdict(entry), "outcome": outcome}
                    )
                    changed += 1
            if changed:
                if self._load_error is not None:
                    raise OSError("diário automático indisponível; histórico existente requer inspeção manual")
                self._persist()
        return changed

    def accepted_count_today(self, *, now: datetime | None = None) -> int:
        """Count accepted executions, failing closed if durable history is unreadable."""
        with self._lock:
            if self._load_error is not None:
                raise OSError("diário automático indisponível; limite diário não pode ser validado")
        return sum(item.accepted for item in self.today(now=now))

    def summary(self) -> dict[str, Any]:
        entries = self.today()
        return {
            "date_utc": datetime.now(timezone.utc).date().isoformat(),
            "total": len(entries),
            "accepted": sum(item.accepted for item in entries),
            "rejected": sum(not item.accepted for item in entries),
            "wins": sum(item.outcome == "WIN" for item in entries),
            "losses": sum(item.outcome == "LOSS" for item in entries),
            "storage_health": "CORRUPTED" if self._load_error else "OK",
            "note": "resultados WIN/LOSS são liquidados em memória de operação; este diário registra o ciclo operacional",
        }
