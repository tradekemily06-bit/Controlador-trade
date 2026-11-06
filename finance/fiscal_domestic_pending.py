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


MAX_PENDING_OFFSET = 1_000_000_000
from zoneinfo import ZoneInfo

from finance.fiscal_taxonomy import BRAZIL_CATEGORIES


class FiscalDomesticPendingQueue:
    def __init__(self, database_path: str = ":memory:") -> None:
        self.database_path = str(database_path)
        self._uri = None
        self._anchor = None
        if self.database_path == ":memory:":
            self._uri = f"file:fiscal_domestic_{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._anchor = sqlite3.connect(self._uri, uri=True, timeout=10)
        else:
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
                CREATE UNIQUE INDEX IF NOT EXISTS ux_fiscal_pending_domestic_owner_id
                ON fiscal_reserve_pending_domestic(owner_id, pending_id)
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS fiscal_pending_domestic_owner_date
                ON fiscal_reserve_pending_domestic(owner_id, occurred_on DESC)
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS fiscal_domestic_pending_reviews (
                    review_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
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
                    FOREIGN KEY(owner_id, pending_id)
                        REFERENCES fiscal_reserve_pending_domestic(owner_id, pending_id)
                        ON DELETE RESTRICT
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS fiscal_domestic_pending_reviews_item
                ON fiscal_domestic_pending_reviews(owner_id, pending_id, created_at DESC)
            """)

    @staticmethod
    def _require_owner(owner_id: str) -> str:
        # Never coerce caller-controlled objects into an authorization key.
        if not isinstance(owner_id, str):
            raise ValueError("identidade proprietária obrigatória e inválida")
        owner = owner_id.strip()
        if not owner or len(owner) > 160:
            raise ValueError("identidade proprietária obrigatória e inválida")
        return owner

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._uri or self.database_path, uri=bool(self._uri), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
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
    def _day(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("occurred_on deve ser texto no formato YYYY-MM-DD")
        raw = value.strip()
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("occurred_on deve usar YYYY-MM-DD") from exc
        if parsed.isoformat() != raw:
            raise ValueError("occurred_on deve usar YYYY-MM-DD")
        return raw

    @staticmethod
    def _text(payload: dict[str, Any], field: str, maximum: int, *, required: bool = False) -> str:
        raw = payload.get(field, "")
        if raw is None and not required:
            raw = ""
        if not isinstance(raw, str):
            raise ValueError(f"{field} deve ser texto")
        value = raw.strip()
        if required and not value:
            raise ValueError(f"{field} é obrigatório e deve ter até {maximum} caracteres")
        if len(value) > maximum:
            raise ValueError(f"{field} deve ter até {maximum} caracteres")
        return value

    def add(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        owner_id = self._require_owner(owner_id)
        if not isinstance(payload, dict):
            raise ValueError("identidade proprietária e payload são obrigatórios")
        reference = self._text(payload, "reference", 160, required=True)
        instrument = self._text(payload, "instrument", 80, required=True)
        if not reference or len(reference) > 160:
            raise ValueError("reference é obrigatório e deve ter até 160 caracteres")
        if not instrument or len(instrument) > 80:
            raise ValueError("instrument é obrigatório e deve ter até 80 caracteres")
        raw_result = payload.get("realized_result_brl")
        result = None
        if raw_result is not None:
            if isinstance(raw_result, bool) or not isinstance(raw_result, (int, float)):
                raise ValueError("realized_result_brl deve ser numérico")
            try:
                result = float(raw_result)
            except (OverflowError, TypeError, ValueError) as exc:
                raise ValueError("realized_result_brl deve ser numérico") from exc
            if result != result or result in (float("inf"), float("-inf")) or abs(result) > 1e12:
                raise ValueError("realized_result_brl deve ser finito e estar dentro do limite")
            result = round(result, 2)
        category_candidate = self._text(payload, "category_candidate", 120)
        if category_candidate and category_candidate not in BRAZIL_CATEGORIES:
            raise ValueError("category_candidate não pertence ao catálogo brasileiro permitido")
        item = {
            "pending_id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "reference": reference,
            "category_candidate": category_candidate,
            "instrument": instrument,
            "market_scope": self._text(payload, "market_scope", 80),
            "occurred_on": self._day(payload.get("occurred_on")),
            "realized_result_brl": result,
            "notes": self._text(payload, "notes", 1000),
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
        owner_id = self._require_owner(owner_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500")
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= MAX_PENDING_OFFSET
        ):
            raise ValueError(
                f"offset deve estar entre 0 e {MAX_PENDING_OFFSET}"
            )
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

    def record_review(self, owner_id: str, pending_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append declared professional review evidence; never classifies or books the item."""
        owner_id = self._require_owner(owner_id)
        if not isinstance(payload, dict):
            raise ValueError("payload deve ser um objeto")
        if not isinstance(pending_id, str):
            raise ValueError("pending_id inválido")
        pending_id = pending_id.strip()
        if not pending_id or len(pending_id) > 80:
            raise ValueError("pending_id inválido")

        def required(name: str, maximum: int) -> str:
            raw = payload.get(name)
            if not isinstance(raw, str):
                raise ValueError(f"{name} deve ser texto")
            value = raw.strip()
            if not value or len(value) > maximum:
                raise ValueError(f"{name} é obrigatório e deve ter até {maximum} caracteres")
            return value

        candidate = required("candidate_classification", 120)
        if candidate not in BRAZIL_CATEGORIES:
            raise ValueError("candidate_classification não pertence ao catálogo brasileiro permitido")
        jurisdiction = required("confirmed_jurisdiction", 120)
        reviewer = required("reviewer_name", 160)
        role = required("reviewer_role", 80).casefold()
        if role not in {"contador", "consultor tributário", "profissional tributário"}:
            raise ValueError("reviewer_role deve identificar um profissional tributário")
        registration = required("professional_registration", 100)
        evidence = required("evidence_reference", 500)
        reviewed_on = self._day(payload.get("reviewed_on"))
        if date.fromisoformat(reviewed_on) > datetime.now(ZoneInfo("America/Sao_Paulo")).date():
            raise ValueError("reviewed_on não pode estar no futuro")
        raw_notes = payload.get("review_notes", "")
        if not isinstance(raw_notes, str):
            raise ValueError("review_notes deve ser texto")
        notes = raw_notes.strip()
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
                "SELECT 1 FROM fiscal_reserve_pending_domestic WHERE owner_id = ? AND pending_id = ?",
                (owner_id, pending_id),
            ).fetchone():
                raise ValueError("pendência não encontrada")
            db.execute(
                """INSERT INTO fiscal_domestic_pending_reviews
                (review_id, owner_id, pending_id, candidate_classification, confirmed_jurisdiction,
                 reviewer_name, reviewer_role, professional_registration, evidence_reference,
                 reviewed_on, review_notes, created_at)
                VALUES (:review_id, :owner_id, :pending_id, :candidate_classification, :confirmed_jurisdiction,
                 :reviewer_name, :reviewer_role, :professional_registration, :evidence_reference,
                 :reviewed_on, :review_notes, :created_at)""",
                review,
            )
        public_review = {key: value for key, value in review.items() if key != "owner_id"}
        return {**public_review, "reviewer_identity_status": "DECLARED_NOT_VERIFIED",
                "professional_registration_verified": False,
                "status_unchanged": "PENDING_CLASSIFICATION",
                "reserve_calculated": False, "tax_rate_available": False}

    def list_reviews(self, owner_id: str, pending_id: str) -> list[dict[str, Any]]:
        owner_id = self._require_owner(owner_id)
        if not isinstance(pending_id, str):
            raise ValueError("pending_id inválido")
        pending_id = pending_id.strip()
        if not pending_id or len(pending_id) > 80:
            raise ValueError("pending_id inválido")
        with self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM fiscal_reserve_pending_domestic WHERE owner_id = ? AND pending_id = ?",
                (owner_id, pending_id),
            ).fetchone():
                raise ValueError("pendência não encontrada")
            rows = db.execute(
                """SELECT * FROM fiscal_domestic_pending_reviews
                WHERE owner_id = ? AND pending_id = ?
                ORDER BY created_at DESC, review_id DESC""",
                (owner_id, pending_id),
            ).fetchall()
        return [{
            **{key: value for key, value in dict(row).items() if key != "owner_id"},
            "reviewer_identity_status": "DECLARED_NOT_VERIFIED",
            "professional_registration_verified": False,
        } for row in rows]

    def summary(self, owner_id: str, as_of: date | None = None) -> dict[str, Any]:
        owner_id = self._require_owner(owner_id)
        today = as_of or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
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
