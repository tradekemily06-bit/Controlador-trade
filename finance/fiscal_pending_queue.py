"""Pending intake for foreign fiscal items; never estimates or books tax reserves."""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator


CURRENCIES = frozenset({"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "BRL"})


class FiscalPendingQueue:
    def __init__(self, database_path: str = ":memory:") -> None:
        self.database_path = str(database_path)
        self._uri = None
        self._anchor = None
        if self.database_path == ":memory:":
            self._uri = f"file:fiscal_pending_{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._anchor = sqlite3.connect(self._uri, uri=True, timeout=5)
        else:
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS fiscal_reserve_pending_foreign (
                    pending_id TEXT PRIMARY KEY,
                    reference TEXT NOT NULL UNIQUE,
                    original_amount REAL NOT NULL,
                    original_currency TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    occurred_on TEXT NOT NULL,
                    fx_rate REAL,
                    fx_date TEXT,
                    fx_source TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status = 'PENDING_CLASSIFICATION'),
                    created_at TEXT NOT NULL
                )
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._uri if self._uri else self.database_path,
                             uri=bool(self._uri), timeout=10)
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
    def _date(value: Any, field: str) -> str:
        raw = str(value or "").strip()
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"{field} deve usar YYYY-MM-DD") from exc
        if parsed.isoformat() != raw:
            raise ValueError(f"{field} deve usar YYYY-MM-DD")
        return raw

    @staticmethod
    def _positive(value: Any, field: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} deve ser numérico") from exc
        if number <= 0 or number != number or number in (float("inf"), float("-inf")) or number > 1e12:
            raise ValueError(f"{field} deve ser positivo e finito")
        return round(number, 8)

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload deve ser um objeto")
        reference = str(payload.get("reference") or "").strip()
        instrument = str(payload.get("instrument") or "").strip()
        jurisdiction = str(payload.get("jurisdiction") or "").strip()
        currency = str(payload.get("original_currency") or "").strip().upper()
        if not reference or len(reference) > 160:
            raise ValueError("reference é obrigatório e deve ter até 160 caracteres")
        if not instrument or len(instrument) > 80:
            raise ValueError("instrument é obrigatório e deve ter até 80 caracteres")
        if not jurisdiction or len(jurisdiction) > 80:
            raise ValueError("jurisdiction é obrigatório e deve ter até 80 caracteres")
        if currency not in CURRENCIES:
            raise ValueError("moeda não suportada")
        amount = self._positive(payload.get("original_amount"), "original_amount")
        occurred_on = self._date(payload.get("occurred_on"), "occurred_on")
        fx_rate = payload.get("fx_rate")
        fx_date = payload.get("fx_date")
        fx_source = str(payload.get("fx_source") or "").strip()
        if fx_rate is not None:
            fx_rate = self._positive(fx_rate, "fx_rate")
            if not fx_date or not fx_source:
                raise ValueError("fx_date e fx_source são obrigatórios quando houver fx_rate")
            fx_date = self._date(fx_date, "fx_date")
            if len(fx_source) > 200:
                raise ValueError("fx_source deve ter até 200 caracteres")
        elif fx_date or fx_source:
            raise ValueError("fx_rate é obrigatório quando forem informados dados cambiais")
        notes = str(payload.get("notes") or "").strip()[:1000]
        item = {
            "pending_id": str(uuid.uuid4()), "reference": reference,
            "original_amount": amount, "original_currency": currency,
            "instrument": instrument, "jurisdiction": jurisdiction,
            "occurred_on": occurred_on, "fx_rate": fx_rate, "fx_date": fx_date,
            "fx_source": fx_source or None, "notes": notes,
            "status": "PENDING_CLASSIFICATION",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            db.execute("INSERT INTO fiscal_reserve_pending_foreign "
                       "(pending_id, reference, original_amount, original_currency, instrument, "
                       "jurisdiction, occurred_on, fx_rate, fx_date, fx_source, notes, status, created_at) "
                       "VALUES (:pending_id, :reference, :original_amount, :original_currency, :instrument, "
                       ":jurisdiction, :occurred_on, :fx_rate, :fx_date, :fx_source, :notes, :status, :created_at)", item)
        return item

    def list_pending(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset deve ser não negativo")
        with self._connect() as db:
            total = int(db.execute("SELECT COUNT(*) FROM fiscal_reserve_pending_foreign").fetchone()[0])
            rows = db.execute("SELECT * FROM fiscal_reserve_pending_foreign "
                              "ORDER BY created_at DESC, pending_id DESC LIMIT ? OFFSET ?",
                              (limit, offset)).fetchall()
        return {"items": [dict(row) for row in rows], "total": total,
                "limit": limit, "offset": offset,
                "note": "Pendências não integram os totais nem geram estimativa de reserva."}
