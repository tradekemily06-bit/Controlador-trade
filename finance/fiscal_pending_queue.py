"""Pending intake for foreign fiscal items; never estimates or books tax reserves."""
from __future__ import annotations

import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Iterator


MAX_PENDING_OFFSET = 1_000_000_000


CURRENCY_CODE_LENGTH = 3
FOREIGN_REVIEW_CANDIDATES = frozenset({
    "FOREIGN_FINANCIAL_INVESTMENT",
    "FOREIGN_ENTITY_CONTROLLED",
    "FOREIGN_CRYPTO",
    "FOREIGN_DERIVATIVE",
})


FIELD_OPTIONS = {
    "tax_residency_at_event": frozenset({"NOT_INFORMED", "BRAZIL", "FOREIGN", "DUAL_OR_UNCERTAIN"}),
    "income_nature": frozenset({"NOT_INFORMED", "CAPITAL_GAIN", "INVESTMENT_INCOME", "TRADING_RESULT", "DIVIDEND", "INTEREST", "RENTAL_INCOME", "OTHER"}),
    "event_type": frozenset({"NOT_INFORMED", "ACQUISITION", "DISPOSAL", "DIVIDEND_RECEIPT", "INTEREST_RECEIPT", "REDEMPTION", "EXCHANGE", "TRANSFER", "OTHER"}),
    "fx_conversion_method": frozenset({"NOT_INFORMED", "NOT_CONVERTED", "PTAX_SELL", "PTAX_BUY", "BROKER_STATEMENT", "BANK_RECEIPT", "OTHER_DOCUMENTED"}),
}


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
                db.execute("""
                    CREATE TRIGGER IF NOT EXISTS fiscal_pending_reviews_no_update
                    BEFORE UPDATE ON fiscal_pending_reviews
                    BEGIN
                        SELECT RAISE(ABORT, 'fiscal review history is append-only');
                    END
                """)
                db.execute("""
                    CREATE TRIGGER IF NOT EXISTS fiscal_pending_reviews_no_delete
                    BEFORE DELETE ON fiscal_pending_reviews
                    BEGIN
                        SELECT RAISE(ABORT, 'fiscal review history is append-only');
                    END
                """)
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
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS fiscal_pending_reviews_no_update
                BEFORE UPDATE ON fiscal_pending_reviews
                BEGIN
                    SELECT RAISE(ABORT, 'fiscal review history is append-only');
                END
            """)
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS fiscal_pending_reviews_no_delete
                BEFORE DELETE ON fiscal_pending_reviews
                BEGIN
                    SELECT RAISE(ABORT, 'fiscal review history is append-only');
                END
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
        if not isinstance(value, str):
            raise ValueError(f"{field} deve ser texto no formato YYYY-MM-DD")
        raw = value.strip()
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"{field} deve usar YYYY-MM-DD") from exc
        if parsed.isoformat() != raw:
            raise ValueError(f"{field} deve usar YYYY-MM-DD")
        return raw

    @staticmethod
    def _reject_future_event_date(value: str, field: str) -> str:
        """Prevent future-dated events or FX evidence from entering the fiscal queue."""
        parsed = date.fromisoformat(value)
        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        if parsed > today:
            raise ValueError(f"{field} não pode estar no futuro")
        return value

    @staticmethod
    def _positive(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} deve ser numérico")
        try:
            number = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{field} deve ser numérico") from exc
        if number <= 0 or number != number or number in (float("inf"), float("-inf")) or number > 1e12:
            raise ValueError(f"{field} deve ser positivo e finito")
        return round(number, 8)

    @staticmethod
    def _optional_nonnegative(payload: dict[str, Any], field: str) -> float | None:
        raw = payload.get(field)
        if raw is None or raw == "":
            return None
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{field} deve ser numérico")
        try:
            value = float(raw)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{field} deve ser numérico") from exc
        if value < 0 or value != value or value in (float("inf"), float("-inf")) or value > 1e12:
            raise ValueError(f"{field} deve ser não negativo e finito")
        return round(value, 8)

    @classmethod
    def _fiscal_details(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "institution": cls._text(payload, "institution", 160),
            "custody_location": cls._text(payload, "custody_location", 120) or "NOT_INFORMED",
            "contract_type": cls._text(payload, "contract_type", 120) or "NOT_INFORMED",
            "acquisition_cost": cls._optional_nonnegative(payload, "acquisition_cost"),
            "transaction_fees": cls._optional_nonnegative(payload, "transaction_fees"),
            "foreign_tax_paid": cls._optional_nonnegative(payload, "foreign_tax_paid"),
        }

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

    @staticmethod
    def _declared_field(payload: dict[str, Any], field: str) -> str:
        raw = payload.get(field, "NOT_INFORMED")
        if raw is None or raw == "":
            raw = "NOT_INFORMED"
        if not isinstance(raw, str):
            raise ValueError(f"{field} deve ser texto")
        value = raw.strip().upper()
        if value not in FIELD_OPTIONS[field]:
            raise ValueError(f"{field} possui opção inválida")
        return value

    @staticmethod
    def _with_fx_planning_preview(item: dict[str, Any]) -> dict[str, Any]:
        """Expose documented currency conversion for planning without tax booking."""
        result = dict(item)
        if "planning_estimate_registered" in result:
            result["planning_estimate_registered"] = bool(result["planning_estimate_registered"])
        currency = str(result.get("original_currency") or "").upper()
        if currency == "BRL":
            rate = 1.0
            result["fx_conversion_status"] = "ALREADY_BRL"
        else:
            rate = result.get("fx_rate")
            method = result.get("fx_conversion_method")
            documented_methods = {
                "PTAX_SELL", "PTAX_BUY", "BROKER_STATEMENT",
                "BANK_RECEIPT", "OTHER_DOCUMENTED",
            }
            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or rate <= 0
                or not math.isfinite(float(rate))
                or method not in documented_methods
                or not result.get("fx_date")
                or not result.get("fx_source")
            ):
                rate = None
                result["fx_conversion_status"] = "FX_NOT_PROVIDED"
            else:
                rate = float(rate)
                result["fx_conversion_status"] = "CONVERTED_FOR_PLANNING_ONLY"

        result["fx_rate_direction"] = "BRL_PER_ORIGINAL_CURRENCY_UNIT"
        if rate is None:
            result["converted_amount_brl_for_planning"] = None
            result["converted_result_brl_for_planning"] = None
            result["converted_acquisition_cost_brl_for_planning"] = None
            result["converted_transaction_fees_brl_for_planning"] = None
            result["converted_foreign_tax_paid_brl_for_planning"] = None
            return result

        def convert(value: Any, *, signed: bool = False) -> float | None:
            if value is None:
                return None
            amount = float(value)
            if not signed:
                amount = abs(amount)
            return round(amount * rate, 2)

        is_result = result.get("record_kind") == "REALIZED_RESULT"
        original_result = result.get("original_result")
        result["converted_amount_brl_for_planning"] = (
            None if is_result else convert(result.get("original_amount"))
        )
        result["converted_result_brl_for_planning"] = (
            convert(original_result, signed=True) if is_result else None
        )
        # This quote belongs to the event date. Acquisition costs and fees may
        # require their own historical dates/quotes; foreign tax paid uses a
        # separate BCB BUY quote on the payment date. Never reuse this quote.
        result["converted_acquisition_cost_brl_for_planning"] = None
        result["converted_transaction_fees_brl_for_planning"] = None
        result["converted_foreign_tax_paid_brl_for_planning"] = None
        result["fx_preview_scope"] = "EVENT_AMOUNT_OR_REALIZED_RESULT_ONLY"
        return result

    def add(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        owner_id = self._require_owner(owner_id)
        if not isinstance(payload, dict):
            raise ValueError("payload deve ser um objeto")
        reference = self._text(payload, "reference", 160, required=True)
        instrument = self._text(payload, "instrument", 80, required=True)
        jurisdiction = self._text(payload, "jurisdiction", 80, required=True)
        currency = self._text(payload, "original_currency", 3, required=True).upper()
        if not reference or len(reference) > 160:
            raise ValueError("reference é obrigatório e deve ter até 160 caracteres")
        if not instrument or len(instrument) > 80:
            raise ValueError("instrument é obrigatório e deve ter até 80 caracteres")
        if not jurisdiction or len(jurisdiction) > 80:
            raise ValueError("jurisdiction é obrigatório e deve ter até 80 caracteres")
        if len(currency) != CURRENCY_CODE_LENGTH or not currency.isascii() or not currency.isalpha():
            raise ValueError("moeda deve ser um código alfabético de três letras")
        amount = self._positive(payload.get("original_amount"), "original_amount")
        occurred_on = self._reject_future_event_date(
            self._date(payload.get("occurred_on"), "occurred_on"), "occurred_on"
        )
        fx_rate = payload.get("fx_rate")
        fx_date = payload.get("fx_date")
        fx_source = self._text(payload, "fx_source", 200)
        if fx_rate is not None:
            fx_rate = self._positive(fx_rate, "fx_rate")
            if not fx_date or not fx_source:
                raise ValueError("fx_date e fx_source são obrigatórios quando houver fx_rate")
            fx_date = self._reject_future_event_date(
                self._date(fx_date, "fx_date"), "fx_date"
            )
            if len(fx_source) > 200:
                raise ValueError("fx_source deve ter até 200 caracteres")
        elif fx_date or fx_source:
            raise ValueError("fx_rate é obrigatório quando forem informados dados cambiais")
        declared = {field: self._declared_field(payload, field) for field in FIELD_OPTIONS}
        if fx_rate is not None and declared["fx_conversion_method"] == "NOT_CONVERTED":
            raise ValueError("fx_conversion_method não pode ser NOT_CONVERTED quando houver cotação")
        if fx_rate is not None and declared["fx_conversion_method"] == "NOT_INFORMED":
            raise ValueError("fx_conversion_method deve ser informado quando houver cotação")
        if fx_rate is None and declared["fx_conversion_method"] not in {"NOT_INFORMED", "NOT_CONVERTED"}:
            raise ValueError("fx_conversion_method exige fx_rate, fx_date e fx_source")
        notes = self._text(payload, "notes", 1000)
        details = self._fiscal_details(payload)
        item = {
            "pending_id": str(uuid.uuid4()), "owner_id": owner_id, "reference": reference,
            "original_amount": amount, "original_currency": currency,
            "instrument": instrument, "jurisdiction": jurisdiction,
            "occurred_on": occurred_on, "fx_rate": fx_rate, "fx_date": fx_date,
            "fx_source": fx_source or None, **declared, **details, "notes": notes,
            "status": "PENDING_CLASSIFICATION",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            db.execute("INSERT INTO fiscal_reserve_pending_foreign "
                       "(pending_id, owner_id, reference, original_amount, original_currency, instrument, "
                       "jurisdiction, occurred_on, fx_rate, fx_date, fx_source, tax_residency_at_event, income_nature, "
                       "event_type, fx_conversion_method, institution, custody_location, contract_type, "
                       "acquisition_cost, transaction_fees, foreign_tax_paid, notes, status, created_at) "
                       "VALUES (:pending_id, :owner_id, :reference, :original_amount, :original_currency, :instrument, "
                       ":jurisdiction, :occurred_on, :fx_rate, :fx_date, :fx_source, :tax_residency_at_event, "
                       ":income_nature, :event_type, :fx_conversion_method, :institution, :custody_location, "
                       ":contract_type, :acquisition_cost, :transaction_fees, :foreign_tax_paid, :notes, :status, :created_at)", item)
        return self._with_fx_planning_preview(
            {key: value for key, value in item.items() if key != "owner_id"}
        )

    def add_realized_result(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Store a signed foreign realized result; it remains pending and outside fiscal totals."""
        owner_id = self._require_owner(owner_id)
        if not isinstance(payload, dict):
            raise ValueError("payload deve ser um objeto")
        reference = self._text(payload, "reference", 160, required=True)
        instrument = self._text(payload, "instrument", 80, required=True)
        jurisdiction = self._text(payload, "jurisdiction", 80, required=True)
        currency = self._text(payload, "original_currency", 3, required=True).upper()
        if not reference or len(reference) > 160:
            raise ValueError("reference é obrigatório e deve ter até 160 caracteres")
        if not instrument or len(instrument) > 80:
            raise ValueError("instrument é obrigatório e deve ter até 80 caracteres")
        if not jurisdiction or len(jurisdiction) > 80:
            raise ValueError("jurisdiction é obrigatório e deve ter até 80 caracteres")
        if len(currency) != CURRENCY_CODE_LENGTH or not currency.isascii() or not currency.isalpha():
            raise ValueError("moeda deve ser um código alfabético de três letras")
        raw_result = payload.get("original_result")
        if isinstance(raw_result, bool) or not isinstance(raw_result, (int, float)):
            raise ValueError("original_result deve ser numérico")
        try:
            result = float(raw_result)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("original_result deve ser numérico") from exc
        if result != result or result in (float("inf"), float("-inf")) or abs(result) > 1e12:
            raise ValueError("original_result deve ser finito e estar dentro do limite")
        result = round(result, 8)
        occurred_on = self._reject_future_event_date(
            self._date(payload.get("occurred_on"), "occurred_on"), "occurred_on"
        )
        fx_rate = payload.get("fx_rate")
        fx_date = payload.get("fx_date")
        fx_source = self._text(payload, "fx_source", 200)
        if fx_rate is not None:
            fx_rate = self._positive(fx_rate, "fx_rate")
            if not fx_date or not fx_source:
                raise ValueError("fx_date e fx_source são obrigatórios quando houver fx_rate")
            fx_date = self._reject_future_event_date(
                self._date(fx_date, "fx_date"), "fx_date"
            )
            if len(fx_source) > 200:
                raise ValueError("fx_source deve ter até 200 caracteres")
        elif fx_date or fx_source:
            raise ValueError("fx_rate é obrigatório quando forem informados dados cambiais")
        declared = {field: self._declared_field(payload, field) for field in FIELD_OPTIONS}
        if fx_rate is not None and declared["fx_conversion_method"] == "NOT_CONVERTED":
            raise ValueError("fx_conversion_method não pode ser NOT_CONVERTED quando houver cotação")
        if fx_rate is not None and declared["fx_conversion_method"] == "NOT_INFORMED":
            raise ValueError("fx_conversion_method deve ser informado quando houver cotação")
        if fx_rate is None and declared["fx_conversion_method"] not in {"NOT_INFORMED", "NOT_CONVERTED"}:
            raise ValueError("fx_conversion_method exige fx_rate, fx_date e fx_source")
        details = self._fiscal_details(payload)
        item = {
            "pending_id": str(uuid.uuid4()), "owner_id": owner_id, "reference": reference,
            "original_amount": abs(result), "original_result": result, "record_kind": "REALIZED_RESULT",
            "original_currency": currency, "instrument": instrument, "jurisdiction": jurisdiction,
            "occurred_on": occurred_on, "fx_rate": fx_rate, "fx_date": fx_date,
            "fx_source": fx_source or None, **declared, **details, "notes": self._text(payload, "notes", 1000),
            "status": "PENDING_CLASSIFICATION", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            db.execute(
                """INSERT INTO fiscal_reserve_pending_foreign
                (pending_id, owner_id, reference, original_amount, original_currency, instrument,
                 jurisdiction, occurred_on, fx_rate, fx_date, fx_source, tax_residency_at_event,
                 income_nature, event_type, fx_conversion_method, institution, custody_location,
                 contract_type, acquisition_cost, transaction_fees, foreign_tax_paid,
                 notes, status, created_at, original_result, record_kind)
                VALUES (:pending_id, :owner_id, :reference, :original_amount, :original_currency,
                 :instrument, :jurisdiction, :occurred_on, :fx_rate, :fx_date, :fx_source,
                 :tax_residency_at_event, :income_nature, :event_type, :fx_conversion_method,
                 :institution, :custody_location, :contract_type, :acquisition_cost,
                 :transaction_fees, :foreign_tax_paid, :notes, :status, :created_at,
                 :original_result, :record_kind)""",
                item,
            )
        return self._with_fx_planning_preview(
            {key: value for key, value in item.items() if key != "owner_id"}
        )

    def record_review(self, owner_id: str, pending_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append professional review evidence; never changes pending status or calculates tax."""
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

        with self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM fiscal_reserve_pending_foreign WHERE owner_id = ? AND pending_id = ?",
                (owner_id, pending_id),
            ).fetchone():
                raise ValueError("pendência não encontrada")

        candidate = required("candidate_classification", 120)
        if candidate not in FOREIGN_REVIEW_CANDIDATES:
            raise ValueError("candidate_classification não pertence ao catálogo estrangeiro permitido")
        jurisdiction = required("confirmed_jurisdiction", 120)
        reviewer = required("reviewer_name", 160)
        role = required("reviewer_role", 80).casefold()
        if role not in {"contador", "consultor tributário", "profissional tributário"}:
            raise ValueError("reviewer_role deve identificar um profissional tributário")
        registration = required("professional_registration", 100)
        evidence = required("evidence_reference", 500)
        reviewed_on = self._date(payload.get("reviewed_on"), "reviewed_on")
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
                "SELECT 1 FROM fiscal_reserve_pending_foreign WHERE owner_id = ? AND pending_id = ?",
                (owner_id, pending_id),
            ).fetchone():
                raise ValueError("pendência não encontrada")
            rows = db.execute(
                "SELECT * FROM fiscal_pending_reviews WHERE owner_id = ? AND pending_id = ? ORDER BY created_at DESC, review_id DESC",
                (owner_id, pending_id),
            ).fetchall()
        return [{**{key: value for key, value in dict(row).items() if key != "owner_id"},
                 "reviewer_identity_status": "DECLARED_NOT_VERIFIED",
                 "professional_registration_verified": False} for row in rows]

    def summary(self, owner_id: str, as_of: date | None = None) -> dict[str, Any]:
        """Return owner-scoped counts by period; never expose values or calculate tax."""
        owner_id = self._require_owner(owner_id)
        reference_day = as_of or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        week_start = date.fromordinal(reference_day.toordinal() - reference_day.weekday())
        periods = {
            "day": (reference_day, reference_day),
            "week": (week_start, reference_day),
            "month": (reference_day.replace(day=1), reference_day),
            "year": (reference_day.replace(month=1, day=1), reference_day),
        }
        with self._connect() as db:
            total = int(db.execute(
                "SELECT COUNT(*) FROM fiscal_reserve_pending_foreign WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()[0])
            planning_estimates_registered = int(db.execute(
                """SELECT COUNT(*) FROM fiscal_reserve_pending_foreign p
                   WHERE p.owner_id = ? AND EXISTS(
                       SELECT 1 FROM fiscal_reserve_entries e
                       WHERE e.owner_id = p.owner_id
                         AND e.category = 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT'
                         AND e.reference = p.reference
                   )""",
                (owner_id,),
            ).fetchone()[0])
            kinds = db.execute(
                """SELECT record_kind, COUNT(*) AS item_count
                   FROM fiscal_reserve_pending_foreign
                   WHERE owner_id = ?
                   GROUP BY record_kind""",
                (owner_id,),
            ).fetchall()
            currencies = db.execute(
                """SELECT DISTINCT original_currency
                   FROM fiscal_reserve_pending_foreign
                   WHERE owner_id = ?
                   ORDER BY original_currency""",
                (owner_id,),
            ).fetchall()
            evidence = db.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(CASE WHEN
                           TRIM(COALESCE(institution, '')) = ''
                           AND LOWER(TRIM(COALESCE(custody_location, ''))) NOT LIKE '%autocust%'
                           AND LOWER(TRIM(COALESCE(custody_location, ''))) NOT LIKE '%self-custod%'
                           THEN 1 ELSE 0 END) AS missing_institution,
                       SUM(CASE WHEN TRIM(COALESCE(custody_location, '')) IN ('', 'NOT_INFORMED') THEN 1 ELSE 0 END) AS missing_custody_location,
                       SUM(CASE WHEN TRIM(COALESCE(contract_type, '')) IN ('', 'NOT_INFORMED', 'NOT_CONFIRMED') THEN 1 ELSE 0 END) AS missing_contract_type,
                       SUM(CASE WHEN
                           (
                               TRIM(COALESCE(institution, '')) = ''
                               AND LOWER(TRIM(COALESCE(custody_location, ''))) NOT LIKE '%autocust%'
                               AND LOWER(TRIM(COALESCE(custody_location, ''))) NOT LIKE '%self-custod%'
                           )
                           OR TRIM(COALESCE(custody_location, '')) IN ('', 'NOT_INFORMED')
                           OR TRIM(COALESCE(contract_type, '')) IN ('', 'NOT_INFORMED', 'NOT_CONFIRMED')
                           THEN 1 ELSE 0 END) AS missing_core_evidence
                   FROM fiscal_reserve_pending_foreign
                   WHERE owner_id = ?""",
                (owner_id,),
            ).fetchone()
            period_counts = {}
            for period_name, (start_day, end_day) in periods.items():
                row = db.execute(
                    """SELECT COUNT(*) AS total,
                              SUM(CASE WHEN record_kind='REALIZED_RESULT' THEN 1 ELSE 0 END) AS realized_results,
                              SUM(CASE WHEN record_kind='ASSET_AMOUNT' THEN 1 ELSE 0 END) AS asset_amounts
                       FROM fiscal_reserve_pending_foreign
                       WHERE owner_id = ? AND occurred_on >= ? AND occurred_on < ?""",
                    (owner_id, start_day.isoformat(), date.fromordinal(end_day.toordinal() + 1).isoformat()),
                ).fetchone()
                period_counts[period_name] = {
                    "start": start_day.isoformat(),
                    "end": end_day.isoformat(),
                    "total": int(row["total"] or 0),
                    "realized_results": int(row["realized_results"] or 0),
                    "asset_amounts": int(row["asset_amounts"] or 0),
                }
        counts = {str(row["record_kind"]): int(row["item_count"]) for row in kinds}
        return {
            "available": True,
            "as_of": reference_day.isoformat(),
            "total": total,
            "realized_results": counts.get("REALIZED_RESULT", 0),
            "asset_amounts": counts.get("ASSET_AMOUNT", 0),
            "planning_estimates_registered": planning_estimates_registered,
            "currencies": [str(row["original_currency"]) for row in currencies],
            "evidence_completeness": {
                "total": int(evidence["total"] or 0),
                "missing_institution": int(evidence["missing_institution"] or 0),
                "missing_custody_location": int(evidence["missing_custody_location"] or 0),
                "missing_contract_type": int(evidence["missing_contract_type"] or 0),
                "missing_core_evidence": int(evidence["missing_core_evidence"] or 0),
            },
            "periods": period_counts,
            "classification_status": "PENDING_CLASSIFICATION",
            "included_in_totals": False,
            "reserve_calculated": False,
        }

    def get_pending(self, owner_id: str, pending_id: str) -> dict[str, Any]:
        owner_id = self._require_owner(owner_id)
        if not isinstance(pending_id, str):
            raise ValueError("pending_id inválido")
        pending_id = pending_id.strip()
        if not pending_id or len(pending_id) > 80:
            raise ValueError("pending_id inválido")
        with self._connect() as db:
            row = db.execute(
                """SELECT p.*,
                   EXISTS(
                       SELECT 1 FROM fiscal_reserve_entries e
                       WHERE e.owner_id = p.owner_id
                         AND e.category = 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT'
                         AND e.reference = p.reference
                   ) AS planning_estimate_registered
                   FROM fiscal_reserve_pending_foreign p
                   WHERE p.owner_id = ? AND p.pending_id = ?""",
                (owner_id, pending_id),
            ).fetchone()
        if row is None:
            raise ValueError("pendência não encontrada")
        return self._with_fx_planning_preview(
            {key: value for key, value in dict(row).items() if key != "owner_id"}
        )

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
            total = int(db.execute("SELECT COUNT(*) FROM fiscal_reserve_pending_foreign WHERE owner_id = ?", (owner_id,)).fetchone()[0])
            rows = db.execute(
                """SELECT p.*,
                   EXISTS(
                       SELECT 1 FROM fiscal_reserve_entries e
                       WHERE e.owner_id = p.owner_id
                         AND e.category = 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT'
                         AND e.reference = p.reference
                   ) AS planning_estimate_registered
                   FROM fiscal_reserve_pending_foreign p
                   WHERE p.owner_id = ?
                   ORDER BY p.created_at DESC, p.pending_id DESC LIMIT ? OFFSET ?""",
                (owner_id, limit, offset),
            ).fetchall()
        return {
            "items": [
                self._with_fx_planning_preview(
                    {key: value for key, value in dict(row).items() if key != "owner_id"}
                )
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "note": "Conversões documentadas são apoio de planejamento; a fila não integra os totais. Estimativas confirmadas aparecem separadamente no livro de reserva.",
        }
