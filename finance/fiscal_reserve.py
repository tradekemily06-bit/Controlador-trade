"""Reserva Fiscal: planning reserve for realized results.

Rates are planning estimates, not a tax calculator or tax advice.
Foreign entries require explicit classification, Brazilian tax residency,
and documented BRL conversion before a planning rate is applied.
Original currency and FX evidence remain preserved in the pending ledger.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo


# Planning rates only. The foreign lane covers explicitly confirmed financial
# applications for a Brazilian tax resident, including eligible virtual assets;
# it is not a generic foreign, controlled-entity, or tax-assessment rate.
# Legal basis: Lei 14.754/2023, art. 2º; RFB Solução de Consulta Cosit 83/2024.
DEFAULT_RATES = {
    "BR_DAY_TRADE": 20.0,
    "BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT": 15.0,
}
MAX_FISCAL_HISTORY_OFFSET = 1_000_000_000
# Reserved legacy marker: user-entered notes must never control fiscal inclusion.
_UNVERIFIED_LEGACY_MARKER = "USER_DECLARED_PENDING_REVIEW"
# Keep the legacy category readable for historical rows, but never configure
# or seed a generic foreign tax percentage.
VALID_CATEGORIES = frozenset({"BR_DAY_TRADE", "BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT", "FOREIGN_FINANCIAL_ASSET"})


@dataclass(frozen=True)
class FiscalReserveEntry:
    entry_id: str
    category: str
    entry_type: str
    realized_result_brl: float
    reserve_rate: float
    reserve_amount_brl: float
    reference: str
    occurred_on: str
    created_at: str
    notes: str


class FiscalReserve:
    """Persistent, auditable reserve ledger; never moves money or authorizes trades."""

    def __init__(self, database_path: str = ":memory:") -> None:
        self.database_path = str(database_path)
        self._memory_uri: str | None = None
        self._memory_anchor: sqlite3.Connection | None = None
        if self.database_path == ":memory:":
            # Keep a shared in-memory database alive across short-lived connections.
            self._memory_uri = f"file:fiscal_reserve_{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._memory_anchor = sqlite3.connect(self._memory_uri, uri=True, timeout=5)
        else:
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._memory_uri:
            connection = sqlite3.connect(self._memory_uri, uri=True, timeout=10)
        else:
            connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        # SQLite disables foreign-key enforcement on every new connection by default.
        # Enable it here so every repository operation honors the migrated schema.
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(fiscal_reserve_settings)")}
            if "owner_id" in columns:
                return
            db.execute("""
                CREATE TABLE IF NOT EXISTS fiscal_reserve_settings (
                    category TEXT PRIMARY KEY,
                    rate REAL NOT NULL CHECK(rate >= 0 AND rate <= 100)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS fiscal_reserve_entries (
                    entry_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    realized_result_brl REAL NOT NULL,
                    reserve_rate REAL NOT NULL,
                    reserve_amount_brl REAL NOT NULL,
                    reference TEXT NOT NULL,
                    occurred_on TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    notes TEXT NOT NULL
                )
            """)
            duplicates = db.execute(
                """SELECT category, reference, COUNT(*) AS total
                FROM fiscal_reserve_entries
                GROUP BY category, reference
                HAVING COUNT(*) > 1
                LIMIT 10"""
            ).fetchall()
            if duplicates:
                details = ", ".join(
                    f"{row['category']}:{row['reference']} ({row['total']})"
                    for row in duplicates
                )
                raise RuntimeError(
                    "Referências fiscais duplicadas encontradas; revisar os registros "
                    f"antes de ativar a proteção de unicidade: {details}"
                )
            db.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS
                ux_fiscal_reserve_category_reference
                ON fiscal_reserve_entries(category, reference)"""
            )
            # Remove the obsolete generic foreign percentage from settings.
            # Historical ledger rows are deliberately preserved for audit.
            db.execute(
                "DELETE FROM fiscal_reserve_settings WHERE category = 'FOREIGN_FINANCIAL_ASSET'"
            )
            for category, rate in DEFAULT_RATES.items():
                db.execute(
                    "INSERT OR IGNORE INTO fiscal_reserve_settings(category, rate) VALUES (?, ?)",
                    (category, rate),
                )

    @staticmethod
    def _category(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("categoria deve ser texto")
        category = value.strip().upper()
        if category not in VALID_CATEGORIES:
            raise ValueError("categoria fiscal inválida")
        return category

    @staticmethod
    def _money(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} deve ser numérico")
        try:
            amount = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{field} deve ser numérico") from exc
        if amount != amount or amount in (float("inf"), float("-inf")):
            raise ValueError(f"{field} deve ser finito")
        if abs(amount) > 1_000_000_000_000:
            raise ValueError(f"{field} excede o limite permitido")
        return round(amount, 2)

    @staticmethod
    def _require_owner(owner_id: str) -> str:
        # Owner IDs are security principals, not values to coerce. Reject
        # booleans, numbers, and custom objects rather than invoking __str__.
        if not isinstance(owner_id, str):
            raise ValueError("identidade proprietária obrigatória e inválida")
        owner = owner_id.strip()
        if not owner or len(owner) > 160:
            raise ValueError("identidade proprietária obrigatória e inválida")
        return owner

    def settings(self, owner_id: str) -> dict[str, float]:
        owner_id = self._require_owner(owner_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT category, rate FROM fiscal_reserve_settings WHERE owner_id = ? ORDER BY category",
                (owner_id,),
            ).fetchall()
        return {row["category"]: float(row["rate"]) for row in rows}

    def update_rate(self, owner_id: str, category: str, rate: Any) -> dict[str, float]:
        owner_id = self._require_owner(owner_id)
        category = self._category(category)
        if category in {"FOREIGN_FINANCIAL_ASSET", "BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT"}:
            raise ValueError("a taxa estrangeira de planejamento é fixa em 15% para a categoria legal específica")
        parsed = self._money(rate, "percentual")
        if not 0 <= parsed <= 100:
            raise ValueError("percentual deve estar entre 0 e 100")
        with self._connect() as db:
            db.execute(
                "INSERT INTO fiscal_reserve_settings(owner_id, category, rate, rate_source) VALUES (?, ?, ?, 'USER_CONFIGURED') "
                "ON CONFLICT(owner_id, category) DO UPDATE SET rate = excluded.rate, rate_source = 'USER_CONFIGURED'",
                (owner_id, category, parsed),
            )
        return self.settings(owner_id)

    def update_rates(self, owner_id: str, rates: dict[str, Any]) -> dict[str, float]:
        owner_id = self._require_owner(owner_id)
        if not isinstance(rates, dict) or set(rates) != {"BR_DAY_TRADE"}:
            raise ValueError("somente o percentual brasileiro pode ser alterado nesta etapa")
        parsed = {}
        for category, value in rates.items():
            parsed[self._category(category)] = self._money(value, "percentual")
        if any(not 0 <= value <= 100 for value in parsed.values()):
            raise ValueError("percentuais devem estar entre 0 e 100")
        with self._connect() as db:
            db.executemany(
                "INSERT INTO fiscal_reserve_settings(owner_id, category, rate, rate_source) VALUES (?, ?, ?, 'USER_CONFIGURED') "
                "ON CONFLICT(owner_id, category) DO UPDATE SET rate = excluded.rate, rate_source = 'USER_CONFIGURED'",
                [(owner_id, category, rate) for category, rate in parsed.items()],
            )
        return self.settings(owner_id)

    def record_realized_result(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        owner_id = self._require_owner(owner_id)
        if not isinstance(payload, dict):
            raise ValueError("payload deve ser um objeto")
        category = self._category(payload.get("category"))
        # The generic legacy foreign category remains history-only. New foreign
        # planning entries use the Brazil-resident financial-investment lane,
        # including virtual assets only when the foreign-custody rule is confirmed.
        if category == "FOREIGN_FINANCIAL_ASSET":
            raise ValueError(
                "resultado internacional não pode ser lançado na categoria genérica; "
                "mantenha-o pendente até classificação tributária e conversão cambial validadas"
            )
        result = self._money(payload.get("realized_result_brl"), "realized_result_brl")
        raw_reference = payload.get("reference")
        if not isinstance(raw_reference, str):
            raise ValueError("reference deve ser texto")
        reference = raw_reference.strip()
        if not reference or len(reference) > 160:
            raise ValueError("reference é obrigatório e deve ter até 160 caracteres")
        raw_occurred_on = payload.get("occurred_on")
        if raw_occurred_on is None:
            occurred_on = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        elif isinstance(raw_occurred_on, str):
            occurred_on = raw_occurred_on.strip()
        else:
            raise ValueError("occurred_on deve ser texto no formato YYYY-MM-DD")
        try:
            parsed_date = datetime.strptime(occurred_on, "%Y-%m-%d").date()
            if parsed_date.isoformat() != occurred_on:
                raise ValueError
        except ValueError as exc:
            raise ValueError("occurred_on deve usar YYYY-MM-DD") from exc
        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        if parsed_date > today:
            raise ValueError("occurred_on não pode estar no futuro")
        raw_notes = payload.get("notes", "")
        if not isinstance(raw_notes, str):
            raise ValueError("notes deve ser texto")
        notes = raw_notes.strip()
        if _UNVERIFIED_LEGACY_MARKER.casefold() in notes.casefold():
            raise ValueError("notes contém marcador interno reservado para registros legados")
        notes_limit = 4000 if category == "BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT" else 1000
        if len(notes) > notes_limit:
            raise ValueError(f"notes deve ter até {notes_limit} caracteres")
        if category == "BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT":
            try:
                evidence = json.loads(notes)
            except (TypeError, ValueError) as exc:
                raise ValueError("estimativa estrangeira exige evidências estruturadas") from exc
            if not isinstance(evidence, dict):
                raise ValueError("estimativa estrangeira exige evidências estruturadas")
            if (
                evidence.get("tax_classification_status") != "USER_DECLARED_PLANNING_ONLY"
                or evidence.get("candidate_classification") not in {"FOREIGN_FINANCIAL_INVESTMENT", "FOREIGN_CRYPTO", "FOREIGN_DERIVATIVE"}
                or evidence.get("tax_residency_at_event") != "BRAZIL"
                or evidence.get("tax_liability_confirmed") is not False
                or evidence.get("fx_rate_direction") != "BRL_PER_ORIGINAL_CURRENCY_UNIT"
                or evidence.get("fx_conversion_status") not in {
                    "CONVERTED_FOR_PLANNING_ONLY", "ALREADY_BRL"
                }
                or evidence.get("legal_rate") != 15.0
                or evidence.get("legal_period") != "ANNUAL_ADJUSTMENT"
            ):
                raise ValueError("estimativa estrangeira exige classificação, residência e conversão confirmadas")
            if evidence.get("candidate_classification") == "FOREIGN_CRYPTO" and (
                evidence.get("crypto_location_rule") != "FOREIGN_INSTITUTION_CUSTODY_OR_TRADING_USER_DECLARED"
                or evidence.get("crypto_location_confirmed") is not True
                or evidence.get("crypto_location_verification") != "USER_DECLARED_NOT_VERIFIED"
            ):
                raise ValueError("criptoativo estrangeiro exige confirmação e evidência de localização por instituição no exterior")
            if evidence.get("candidate_classification") == "FOREIGN_DERIVATIVE" and (
                evidence.get("derivative_location_rule") != "FOREIGN_INSTITUTION_AND_CONTRACT_JURISDICTION_USER_DECLARED"
                or evidence.get("derivative_location_confirmed") is not True
                or evidence.get("derivative_location_verification") != "USER_DECLARED_NOT_VERIFIED"
                or evidence.get("derivative_result_basis_confirmed") is not True
            ):
                raise ValueError("derivativo estrangeiro exige confirmação da instituição, jurisdição e base do resultado")
            if occurred_on < "2024-01-01":
                raise ValueError("a estimativa de 15% aplica-se a eventos a partir de 01/01/2024")
            if evidence.get("fx_conversion_status") == "CONVERTED_FOR_PLANNING_ONLY":
                fx_rate = evidence.get("fx_rate")
                fx_source = evidence.get("fx_source")
                fx_date = evidence.get("fx_date")
                fx_method = evidence.get("fx_conversion_method")
                if (
                    isinstance(fx_rate, bool)
                    or not isinstance(fx_rate, (int, float))
                    or not math.isfinite(float(fx_rate))
                    or fx_rate <= 0
                    or not isinstance(fx_date, str)
                    or fx_date != occurred_on
                    or not isinstance(fx_source, str)
                    or not fx_source.strip()
                    or not any(token in fx_source.casefold() for token in ("bcb", "banco central", "ptax"))
                    or fx_method != "PTAX_SELL"
                ):
                    raise ValueError(
                        "estimativa exige PTAX de venda do BCB, fonte identificada e data igual à do evento"
                    )
            elif evidence.get("original_currency") != "BRL":
                raise ValueError("conversão direta só é válida para registros originalmente em BRL")
        with self._connect() as db:
            # Serialize writers before checking the idempotency key. The unique
            # index remains the final guard if multiple workers race.
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT entry_id FROM fiscal_reserve_entries WHERE owner_id = ? AND category = ? AND reference = ?",
                (owner_id, category, reference),
            ).fetchone()
            if existing is not None:
                raise ValueError("esta referência já foi registrada nesta categoria")
            row = db.execute(
                "SELECT rate FROM fiscal_reserve_settings WHERE owner_id = ? AND category = ?",
                (owner_id, category),
            ).fetchone()
            rate = float(row["rate"])
            # A negative result is recorded, but no automatic tax-loss carryforward
            # or offset is inferred; those rules require jurisdiction-specific review.
            reserve_amount = round(max(result, 0.0) * rate / 100.0, 2)
            entry = FiscalReserveEntry(
                entry_id=str(uuid.uuid4()),
                category=category,
                entry_type="REALIZED_RESULT",
                realized_result_brl=result,
                reserve_rate=rate,
                reserve_amount_brl=reserve_amount,
                reference=reference,
                occurred_on=occurred_on,
                created_at=datetime.now(timezone.utc).isoformat(),
                notes=notes,
            )
            db.execute(
                """INSERT INTO fiscal_reserve_entries
                (entry_id, owner_id, category, entry_type, realized_result_brl, reserve_rate,
                 reserve_amount_brl, reference, occurred_on, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.entry_id, owner_id, entry.category, entry.entry_type, entry.realized_result_brl, entry.reserve_rate, entry.reserve_amount_brl, entry.reference, entry.occurred_on, entry.created_at, entry.notes),
            )
        return asdict(entry)

    def summary(
        self,
        owner_id: str,
        as_of: date | None = None,
        history_limit: int = 100,
        history_offset: int = 0,
    ) -> dict[str, Any]:
        owner_id = self._require_owner(owner_id)
        if isinstance(history_limit, bool) or not isinstance(history_limit, int) or not 1 <= history_limit <= 500:
            raise ValueError("history_limit deve estar entre 1 e 500")
        if (
            isinstance(history_offset, bool)
            or not isinstance(history_offset, int)
            or not 0 <= history_offset <= MAX_FISCAL_HISTORY_OFFSET
        ):
            raise ValueError(
                f"history_offset deve estar entre 0 e {MAX_FISCAL_HISTORY_OFFSET}"
            )
        rates = self.settings(owner_id)
        reference_day = as_of or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        week_start = reference_day.fromordinal(reference_day.toordinal() - reference_day.weekday())
        periods = {
            "day": (reference_day, reference_day),
            "week": (week_start, reference_day),
            "month": (reference_day.replace(day=1), reference_day),
            "year": (reference_day.replace(month=1, day=1), reference_day),
        }
        period_totals: dict[str, dict[str, Any]] = {}
        categories: dict[str, dict[str, Any]] = {}
        with self._connect() as db:
            for period_name, (start_day, end_day) in periods.items():
                row = db.execute(
                    """SELECT COUNT(*) AS count,
                    COALESCE(SUM(realized_result_brl), 0) AS realized_result_brl,
                    COALESCE(SUM(reserve_amount_brl), 0) AS reserve_amount_brl
                    FROM fiscal_reserve_entries
                    WHERE owner_id = ? AND category IN ('BR_DAY_TRADE', 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT')
                    AND notes NOT LIKE ? AND occurred_on >= ? AND occurred_on < ?""",
                    (owner_id, "%USER_DECLARED_PENDING_REVIEW%", start_day.isoformat(), date.fromordinal(end_day.toordinal() + 1).isoformat()),
                ).fetchone()
                period_totals[period_name] = {
                    "start": start_day.isoformat(),
                    "end": end_day.isoformat(),
                    "entries": int(row["count"]),
                    "realized_result_brl": round(float(row["realized_result_brl"]), 2),
                    "reserve_amount_brl": round(float(row["reserve_amount_brl"]), 2),
                }
            year_start = date(reference_day.year, 1, 1)
            monthly_rows = db.execute(
                """SELECT substr(occurred_on, 6, 2) AS month,
                COUNT(*) AS count,
                COALESCE(SUM(realized_result_brl), 0) AS realized_result_brl,
                COALESCE(SUM(reserve_amount_brl), 0) AS reserve_amount_brl
                FROM fiscal_reserve_entries
                WHERE owner_id = ? AND category IN ('BR_DAY_TRADE', 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT')
                AND notes NOT LIKE ? AND occurred_on >= ? AND occurred_on <= ?
                GROUP BY substr(occurred_on, 6, 2)""",
                (
                    owner_id,
                    "%USER_DECLARED_PENDING_REVIEW%",
                    year_start.isoformat(),
                    reference_day.isoformat(),
                ),
            ).fetchall()
            monthly_by_number = {int(row["month"]): row for row in monthly_rows}
            monthly_planning = []
            for month_number in range(1, 13):
                row = monthly_by_number.get(month_number)
                monthly_planning.append({
                    "month": f"{reference_day.year:04d}-{month_number:02d}",
                    "entries": int(row["count"]) if row else 0,
                    "realized_result_brl": round(float(row["realized_result_brl"]), 2) if row else 0.0,
                    "reserve_amount_brl": round(float(row["reserve_amount_brl"]), 2) if row else 0.0,
                })
            for category in sorted(VALID_CATEGORIES):
                row = db.execute(
                    """SELECT COUNT(*) AS count,
                    COALESCE(SUM(realized_result_brl), 0) AS realized_result_brl,
                    COALESCE(SUM(reserve_amount_brl), 0) AS reserve_amount_brl
                    FROM fiscal_reserve_entries WHERE owner_id = ? AND category = ?
                    AND (? = 'FOREIGN_FINANCIAL_ASSET' OR notes NOT LIKE ?)""",
                    (owner_id, category, category, "%USER_DECLARED_PENDING_REVIEW%"),
                ).fetchone()
                if category == "FOREIGN_FINANCIAL_ASSET":
                    # Legacy foreign rows remain in history for audit only.
                    # They are unclassified and must never contribute to reserve totals.
                    categories[category] = {
                        "entries": int(row["count"]),
                        "realized_result_brl": 0.0,
                        "reserve_amount_brl": 0.0,
                        "classification_status": "PENDING_CLASSIFICATION",
                        "rate_available": False,
                    }
                else:
                    source_row = db.execute(
                        "SELECT rate_source FROM fiscal_reserve_settings WHERE owner_id = ? AND category = ?",
                        (owner_id, category),
                    ).fetchone()
                    rate_source = (
                        str(source_row["rate_source"])
                        if source_row is not None
                        and source_row["rate_source"] in {"DEFAULT", "USER_CONFIGURED", "LEGACY_UNKNOWN"}
                        else ("DEFAULT" if category in DEFAULT_RATES else "LEGACY_UNKNOWN")
                    )
                    categories[category] = {
                        "rate": rates.get(category, DEFAULT_RATES.get(category, 0.0)),
                        "rate_source": rate_source,
                        "entries": int(row["count"]),
                        "realized_result_brl": round(float(row["realized_result_brl"]), 2),
                        "reserve_amount_brl": round(float(row["reserve_amount_brl"]), 2),
                    }
            total = db.execute(
                """SELECT COALESCE(SUM(reserve_amount_brl), 0) AS total
                FROM fiscal_reserve_entries WHERE owner_id = ? AND category IN ('BR_DAY_TRADE', 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT')
                AND notes NOT LIKE ?""",
                (owner_id, "%USER_DECLARED_PENDING_REVIEW%"),
            ).fetchone()
            foreign_annual_rows = db.execute(
                """SELECT occurred_on, realized_result_brl, notes
                FROM fiscal_reserve_entries
                WHERE owner_id = ?
                  AND category = 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT'
                  AND occurred_on >= ? AND occurred_on <= ?
                  AND notes NOT LIKE ?
                ORDER BY occurred_on, created_at, entry_id""",
                (
                    owner_id,
                    year_start.isoformat(),
                    reference_day.isoformat(),
                    "%USER_DECLARED_PENDING_REVIEW%",
                ),
            ).fetchall()
            foreign_gains = 0.0
            foreign_declared_losses = 0.0
            foreign_annual_entries = 0
            for foreign_row in foreign_annual_rows:
                try:
                    evidence = json.loads(str(foreign_row["notes"] or ""))
                except (TypeError, ValueError):
                    continue
                if not isinstance(evidence, dict) or (
                    evidence.get("tax_classification_status") != "USER_DECLARED_PLANNING_ONLY"
                    or evidence.get("candidate_classification") != "FOREIGN_FINANCIAL_INVESTMENT"
                    or evidence.get("tax_residency_at_event") != "BRAZIL"
                    or evidence.get("legal_period") != "ANNUAL_ADJUSTMENT"
                    or evidence.get("tax_liability_confirmed") is not False
                ):
                    continue
                amount = float(foreign_row["realized_result_brl"])
                foreign_annual_entries += 1
                if amount > 0:
                    foreign_gains += amount
                elif amount < 0:
                    # A negative cashflow is not automatically a deductible
                    # financial-application loss. Restrict this informational
                    # scenario to declared realized disposal/redemption results.
                    if (
                        evidence.get("income_nature") in {"CAPITAL_GAIN", "TRADING_RESULT"}
                        and evidence.get("event_type") in {"DISPOSAL", "REDEMPTION"}
                    ):
                        foreign_declared_losses += abs(amount)
            foreign_net_scenario = round(max(foreign_gains - foreign_declared_losses, 0.0), 2)
            foreign_rate = rates.get(
                "BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT",
                DEFAULT_RATES["BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT"],
            )
            foreign_annual_scenario = {
                "year": reference_day.year,
                "as_of": reference_day.isoformat(),
                "entries": foreign_annual_entries,
                "gross_positive_results_brl": round(foreign_gains, 2),
                "declared_losses_brl": round(foreign_declared_losses, 2),
                "net_result_after_declared_losses_brl": foreign_net_scenario,
                "scenario_reserve_brl": round(foreign_net_scenario * foreign_rate / 100.0, 2),
                "gross_entry_reserve_brl": round(foreign_gains * foreign_rate / 100.0, 2),
                "loss_offset_scenario_brl": round(
                    min(foreign_gains, foreign_declared_losses) * foreign_rate / 100.0, 2
                ),
                "kind": "USER_DECLARED_ANNUAL_SCENARIO_ONLY",
                "loss_documentation_verified": False,
                "loss_carryforward_calculated": False,
                "foreign_tax_credits_calculated": False,
                "tax_assessment": False,
                "description": (
                    "Simulação anual com perdas declaradas pelo usuário; documentos não são "
                    "validados pelo sistema. Não representa compensação fiscal confirmada, "
                    "não inclui saldo de perdas de anos anteriores nem créditos de imposto estrangeiro."
                ),
            }
            history_total = int(db.execute(
                "SELECT COUNT(*) AS total FROM fiscal_reserve_entries WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()["total"])
            history = db.execute(
                """SELECT * FROM fiscal_reserve_entries WHERE owner_id = ?
                ORDER BY occurred_on DESC, created_at DESC, entry_id DESC
                LIMIT ? OFFSET ?""",
                (owner_id, history_limit, history_offset),
            ).fetchall()
        return {
            "name": "Reserva Fiscal",
            "currency": "BRL",
            "categories": categories,
            "total_reserved_brl": round(float(total["total"]), 2),
            "periods": period_totals,
            "monthly_planning": {
                "year": reference_day.year,
                "months": monthly_planning,
                "kind": "PLANNING_ESTIMATE_ONLY",
                "tax_assessment": False,
            },
            "foreign_annual_scenario": foreign_annual_scenario,
            "as_of": reference_day.isoformat(),
            "history": [{key: value for key, value in dict(item).items() if key != "owner_id"} for item in history],
            "history_page": {
                "limit": history_limit,
                "offset": history_offset,
                "returned": len(history),
                "total": history_total,
                "has_more": history_offset + len(history) < history_total,
            },
            "reserve_semantics": {
                "kind": "PLANNING_ESTIMATE_ONLY",
                "tax_liability_confirmed": False,
                "monthly_tax_assessment": False,
                "monthly_loss_offsets_calculated": False,
                "irrf_credits_calculated": False,
                "positive_entry_only": True,
                "description": "Estimativa de separação financeira por lançamento positivo; não é apuração mensal nem imposto devido.",
            },
            "limitations": [
                "Estimativa de planejamento; não representa imposto apurado ou devido.",
                "Lançamentos manuais BR_DAY_TRADE dependem de declaração do usuário; elegibilidade de mercado não é verificada independentemente.",
                "Resultados negativos são registrados, mas compensações fiscais não são calculadas.",
                "Registros MT5 com classificação declarada pelo usuário e ainda não verificada permanecem fora dos totais, mesmo se existirem no histórico legado.",
                "Aplicações financeiras no exterior só entram em estimativa após confirmação da categoria, residência fiscal brasileira, resultado realizado e câmbio documentado; criptoativos e entidades controladas permanecem pendentes.",
                "A regra de 15% desta estimativa vale para eventos a partir de 01/01/2024; eventos anteriores exigem revisão separada.",
                "Imposto pago no exterior e compensação de prejuízos não são calculados.",
                "Nenhum valor é transferido ou movimentado pela Reserva Fiscal.",
            ],
        }
