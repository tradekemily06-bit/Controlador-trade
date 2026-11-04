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
            columns = {row["name"] for row in db.execute("PRAGMA table_info(fiscal_reserve_pending_foreign)")}
            if "owner_id" in columns:
                return
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
                    created_at TEXT NOT NULL,
                    original_result REAL,
                    record_kind TEXT NOT NULL DEFAULT 'ASSET_AMOUNT'
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS fiscal_pending_reviews (
                    review_id TEXT PRIMARY KEY,
                    pending_id TEXT NOT NULL,
                    candidate_classification TEXT NOT NULL,
                    confirmed_jurisdiction TEXT NOT NULL,
                    reviewer_name TEXT NOT NULL,
                    reviewer_role TEXT NOT NULL,
                    professional_registration TEXT NOT NULL,
                    evidence_reference TEXT NOT NULL,
                    reviewed_on TEXT NOT NULL,
                    review_notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(pending_id) REFERENCES fiscal_reserve_pending_foreign(pending_id)
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS fiscal_pending_reviews_item ON fiscal_pending_reviews(pending_id, created_at DESC)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._uri if self._uri else self.database_path,
                             uri=bool(self._uri), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        # SQLite foreign-key enforcement is connection-local and disabled by default.
        db.execute("PRAGMA foreign_keys = ON")
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
        if isinstance(value, bool):
            raise ValueError(f"{field} deve ser numérico")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} deve ser numérico") from exc
        if number <= 0 or number != number or number in (float("inf"), float("-inf")) or number > 1e12:
            raise ValueError(f"{field} deve ser positivo e finito")
        return round(number, 8)

    def add(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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
            "pending_id": str(uuid.uuid4()), "owner_id": owner_id, "reference": reference,
            "original_amount": amount, "original_currency": currency,
            "instrument": instrument, "jurisdiction": jurisdiction,
            "occurred_on": occurred_on, "fx_rate": fx_rate, "fx_date": fx_date,
            "fx_source": fx_source or None, "notes": notes,
            "status": "PENDING_CLASSIFICATION",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            db.execute("INSERT INTO fiscal_reserve_pending_foreign "
                       "(pending_id, owner_id, reference, original_amount, original_currency, instrument, "
                       "jurisdiction, occurred_on, fx_rate, fx_date, fx_source, notes, status, created_at) "
                       "VALUES (:pending_id, :owner_id, :reference, :original_amount, :original_currency, :instrument, "
                       ":jurisdiction, :occurred_on, :fx_rate, :fx_date, :fx_source, :notes, :status, :created_at)", item)
        return {key: value for key, value in item.items() if key != "owner_id"}

    def add_realized_result(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Store a signed foreign realized result; it remains pending and outside fiscal totals."""
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
        raw_result = payload.get("original_result")
        if isinstance(raw_result, bool):
            raise ValueError("original_result deve ser numérico")
        try:
            result = float(raw_result)
        except (TypeError, ValueError) as exc:
            raise ValueError("original_result deve ser numérico") from exc
        if result != result or result in (float("inf"), float("-inf")) or abs(result) > 1e12:
            raise ValueError("original_result deve ser finito e estar dentro do limite")
        result = round(result, 8)
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
        item = {
            "pending_id": str(uuid.uuid4()), "owner_id": owner_id, "reference": reference,
            "original_amount": abs(result), "original_result": result, "record_kind": "REALIZED_RESULT",
            "original_currency": currency, "instrument": instrument, "jurisdiction": jurisdiction,
            "occurred_on": occurred_on, "fx_rate": fx_rate, "fx_date": fx_date,
            "fx_source": fx_source or None, "notes": str(payload.get("notes") or "").strip()[:1000],
            "status": "PENDING_CLASSIFICATION", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            db.execute(
                """INSERT INTO fiscal_reserve_pending_foreign
                (pending_id, owner_id, reference, original_amount, original_currency, instrument,
                 jurisdiction, occurred_on, fx_rate, fx_date, fx_source, notes, status, created_at,
                 original_result, record_kind)
                VALUES (:pending_id, :owner_id, :reference, :original_amount, :original_currency,
                 :instrument, :jurisdiction, :occurred_on, :fx_rate, :fx_date, :fx_source,
                 :notes, :status, :created_at, :original_result, :record_kind)""",
                item,
            )
        return {key: value for key, value in item.items() if key != "owner_id"}

    def record_review(self, owner_id: str, pending_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append professional review evidence; never changes pending status or calculates tax."""
        if not isinstance(payload, dict):
            raise ValueError("payload deve ser um objeto")
        pending_id = str(pending_id or "").strip()
        if not pending_id or len(pending_id) > 80:
            raise ValueError("pending_id inválido")

        def required(name: str, maximum: int) -> str:
            value = str(payload.get(name) or "").strip()
            if not value or len(value) > maximum:
                raise ValueError(f"{name} é obrigatório e deve ter até {maximum} caracteres")
            return value

        candidate = required("candidate_classification", 120)
        jurisdiction = required("confirmed_jurisdiction", 120)
        reviewer = required("reviewer_name", 160)
        role = required("reviewer_role", 80).casefold()
        if role not in {"contador", "consultor tributário", "profissional tributário"}:
            raise ValueError("reviewer_role deve identificar um profissional tributário")
        registration = required("professional_registration", 100)
        evidence = required("evidence_reference", 500)
        reviewed_on = self._date(payload.get("reviewed_on"), "reviewed_on")
        notes = str(payload.get("review_notes") or "").strip()
        if len(notes) > 2000:
            raise ValueError("review_notes deve ter até 2000 caracteres")

        review = {
            "review_id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "pending_id": pending_id,
            "candidate_classification": candidate,
            "confirmed_jurisdiction": jurisdiction,
            "reviewer_name": reviewer,
            "reviewer_role": role,
            "professional_registration": registration,
            "evidence_reference": evidence,
            "reviewed_on": reviewed_on,
            "review_notes": notes,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM fiscal_reserve_pending_foreign WHERE owner_id = ? AND pending_id = ?",
                (owner_id, pending_id),
            ).fetchone():
                raise ValueError("pendência não encontrada")
            db.execute(
                """INSERT INTO fiscal_pending_reviews
                (review_id, owner_id, pending_id, candidate_classification, confirmed_jurisdiction,
                 reviewer_name, reviewer_role, professional_registration, evidence_reference,
                 reviewed_on, review_notes, created_at)
                VALUES (:review_id, :owner_id, :pending_id, :candidate_classification, :confirmed_jurisdiction,
                 :reviewer_name, :reviewer_role, :professional_registration, :evidence_reference,
                 :reviewed_on, :review_notes, :created_at)""",
                review,
            )
        public_review = {key: value for key, value in review.items() if key != "owner_id"}
        return {**public_review, "status_unchanged": "PENDING_CLASSIFICATION",
                "reserve_calculated": False, "tax_rate_available": False}

    def list_reviews(self, owner_id: str, pending_id: str) -> list[dict[str, Any]]:
        pending_id = str(pending_id or "").strip()
        with self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM fiscal_reserve_pending_foreign WHERE owner_id = ? AND pending_id = ?",
                (owner_id, pending_id),
            ).fetchone():
                raise ValueError("pendência não encontrada")
            rows = db.execute(
                "SELECT * FROM fiscal_pending_reviews WHERE owner_id = ? AND pending_id = ? ORDER BY created_at DESC, review_id DESC",
                (owner_id, pending_id),
            ).fetchall()
        return [{key: value for key, value in dict(row).items() if key != "owner_id"} for row in rows]

    def list_pending(self, owner_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset deve ser não negativo")
        with self._connect() as db:
            total = int(db.execute("SELECT COUNT(*) FROM fiscal_reserve_pending_foreign WHERE owner_id = ?", (owner_id,)).fetchone()[0])
            rows = db.execute("SELECT * FROM fiscal_reserve_pending_foreign WHERE owner_id = ? "
                              "ORDER BY created_at DESC, pending_id DESC LIMIT ? OFFSET ?",
                              (owner_id, limit, offset)).fetchall()
        return {"items": [{key: value for key, value in dict(row).items() if key != "owner_id"} for row in rows], "total": total,
                "limit": limit, "offset": offset,
                "note": "Pendências não integram os totais nem geram estimativa de reserva."}
