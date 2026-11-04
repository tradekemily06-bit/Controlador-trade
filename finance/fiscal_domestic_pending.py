"""Brazilian domestic fiscal intake kept separate from foreign pending records.

This queue stores evidence only. It never estimates tax or contributes to reserve totals.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class FiscalDomesticPendingQueue:
    def __init__(self, database_path: str = ":memory:") -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS fiscal_reserve_pending_domestic (
                    pending_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    category_candidate TEXT NOT NULL DEFAULT '',
                    instrument TEXT NOT NULL,
                    market_scope TEXT NOT NULL DEFAULT '',
                    occurred_on TEXT NOT NULL,
                    realized_result_brl REAL,
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status = 'PENDING_CLASSIFICATION'),
                    created_at TEXT NOT NULL,
                    UNIQUE(owner_id, reference)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS fiscal_pending_domestic_owner_date
                ON fiscal_reserve_pending_domestic(owner_id, occurred_on DESC)
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _day(value: Any) -> str:
        raw = str(value or "").strip()
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("occurred_on deve usar YYYY-MM-DD") from exc
        if parsed.isoformat() != raw:
            raise ValueError("occurred_on deve usar YYYY-MM-DD")
        return raw

    def add(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not owner_id or not isinstance(payload, dict):
            raise ValueError("identidade proprietária e payload são obrigatórios")
        reference = str(payload.get("reference") or "").strip()
        instrument = str(payload.get("instrument") or "").strip()
        if not reference or len(reference) > 160:
            raise ValueError("reference é obrigatório e deve ter até 160 caracteres")
        if not instrument or len(instrument) > 80:
            raise ValueError("instrument é obrigatório e deve ter até 80 caracteres")
        raw_result = payload.get("realized_result_brl")
        result = None
        if raw_result is not None:
            if isinstance(raw_result, bool):
                raise ValueError("realized_result_brl deve ser numérico")
            try:
                result = float(raw_result)
            except (TypeError, ValueError) as exc:
                raise ValueError("realized_result_brl deve ser numérico") from exc
            if result != result or result in (float("inf"), float("-inf")) or abs(result) > 1e12:
                raise ValueError("realized_result_brl deve ser finito e estar dentro do limite")
            result = round(result, 2)
        item = {
            "pending_id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "reference": reference,
            "category_candidate": str(payload.get("category_candidate") or "").strip()[:120],
            "instrument": instrument,
            "market_scope": str(payload.get("market_scope") or "").strip()[:80],
            "occurred_on": self._day(payload.get("occurred_on")),
            "realized_result_brl": result,
            "notes": str(payload.get("notes") or "").strip()[:1000],
            "status": "PENDING_CLASSIFICATION",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            db.execute("""
                INSERT INTO fiscal_reserve_pending_domestic
                (pending_id,owner_id,reference,category_candidate,instrument,market_scope,
                 occurred_on,realized_result_brl,notes,status,created_at)
                VALUES (:pending_id,:owner_id,:reference,:category_candidate,:instrument,
                 :market_scope,:occurred_on,:realized_result_brl,:notes,:status,:created_at)
            """, item)
        return {key: value for key, value in item.items() if key != "owner_id"}

    def list_pending(self, owner_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset deve ser não negativo")
        with self._connect() as db:
            total = int(db.execute(
                "SELECT COUNT(*) FROM fiscal_reserve_pending_domestic WHERE owner_id = ?", (owner_id,)
            ).fetchone()[0])
            rows = db.execute("""
                SELECT pending_id,reference,category_candidate,instrument,market_scope,
                       occurred_on,realized_result_brl,notes,status,created_at
                FROM fiscal_reserve_pending_domestic
                WHERE owner_id = ?
                ORDER BY occurred_on DESC,created_at DESC,pending_id DESC
                LIMIT ? OFFSET ?
            """, (owner_id, limit, offset)).fetchall()
        return {"items": [dict(row) for row in rows], "total": total,
                "limit": limit, "offset": offset,
                "included_in_totals": False, "reserve_calculated": False}

    def summary(self, owner_id: str, as_of: date | None = None) -> dict[str, Any]:
        today = as_of or date.today()
        week = date.fromordinal(today.toordinal() - today.weekday())
        bounds = {
            "day": (today, today),
            "week": (week, today),
            "month": (today.replace(day=1), today),
            "year": (today.replace(month=1, day=1), today),
        }
        periods = {}
        with self._connect() as db:
            total = int(db.execute(
                "SELECT COUNT(*) FROM fiscal_reserve_pending_domestic WHERE owner_id = ?", (owner_id,)
            ).fetchone()[0])
            for name, (start, end) in bounds.items():
                row = db.execute("""
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN realized_result_brl IS NOT NULL THEN 1 ELSE 0 END) AS results
                    FROM fiscal_reserve_pending_domestic
                    WHERE owner_id = ? AND occurred_on >= ? AND occurred_on < ?
                """, (owner_id, start.isoformat(), date.fromordinal(end.toordinal()+1).isoformat())).fetchone()
                periods[name] = {"start": start.isoformat(), "end": end.isoformat(),
                                 "total": int(row["total"] or 0),
                                 "results": int(row["results"] or 0)}
        return {"available": True, "as_of": today.isoformat(), "total": total,
                "periods": periods, "classification_status": "PENDING_CLASSIFICATION",
                "included_in_totals": False, "reserve_calculated": False}
