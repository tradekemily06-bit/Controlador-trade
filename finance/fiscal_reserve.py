"""Reserva Fiscal: earmarked planning reserve for realized trading results.

Rates are configurable planning defaults, not a tax calculator or tax advice.
Foreign results require an explicit classification before a rate is applied.
All monetary inputs are stored in BRL; FX conversion must happen upstream and
the original currency/rate should be retained by a future import adapter.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo


DEFAULT_RATES = {
    "BR_DAY_TRADE": 20.0,
}
# Keep the legacy category readable for historical rows, but never configure
# or seed a generic foreign tax percentage.
VALID_CATEGORIES = frozenset({"BR_DAY_TRADE", "FOREIGN_FINANCIAL_ASSET"})


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
        category = str(value or "").strip().upper()
        if category not in VALID_CATEGORIES:
            raise ValueError("categoria deve ser BR_DAY_TRADE ou FOREIGN_FINANCIAL_ASSET")
        return category

    @staticmethod
    def _money(value: Any, field: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{field} deve ser numérico")
        try:
            amount = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} deve ser numérico") from exc
        if amount != amount or amount in (float("inf"), float("-inf")):
            raise ValueError(f"{field} deve ser finito")
        if abs(amount) > 1_000_000_000_000:
            raise ValueError(f"{field} excede o limite permitido")
        return round(amount, 2)

    def settings(self) -> dict[str, float]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT category, rate FROM fiscal_reserve_settings ORDER BY category"
            ).fetchall()
        return {row["category"]: float(row["rate"]) for row in rows}

    def update_rate(self, category: str, rate: Any) -> dict[str, float]:
        category = self._category(category)
        if category == "FOREIGN_FINANCIAL_ASSET":
            raise ValueError("percentual internacional genérico não pode ser alterado sem classificação validada")
        parsed = self._money(rate, "percentual")
        if not 0 <= parsed <= 100:
            raise ValueError("percentual deve estar entre 0 e 100")
        with self._connect() as db:
            db.execute(
                "INSERT INTO fiscal_reserve_settings(category, rate) VALUES (?, ?) "
                "ON CONFLICT(category) DO UPDATE SET rate = excluded.rate",
                (category, parsed),
            )
        return self.settings()

    def update_rates(self, rates: dict[str, Any]) -> dict[str, float]:
        if not isinstance(rates, dict) or set(rates) != {"BR_DAY_TRADE"}:
            raise ValueError("somente o percentual brasileiro pode ser alterado nesta etapa")
        parsed = {}
        for category, value in rates.items():
            parsed[self._category(category)] = self._money(value, "percentual")
        if any(not 0 <= value <= 100 for value in parsed.values()):
            raise ValueError("percentuais devem estar entre 0 e 100")
        with self._connect() as db:
            db.executemany(
                "INSERT INTO fiscal_reserve_settings(category, rate) VALUES (?, ?) "
                "ON CONFLICT(category) DO UPDATE SET rate = excluded.rate",
                list(parsed.items()),
            )
        return self.settings()

    def record_realized_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload deve ser um objeto")
        category = self._category(payload.get("category"))
        # The generic foreign category is retained for historical rows and
        # configuration compatibility only. New foreign results must not be
        # reserved until instrument/jurisdiction/FX classification is explicit.
        if category == "FOREIGN_FINANCIAL_ASSET":
            raise ValueError(
                "resultado internacional não pode ser lançado na categoria genérica; "
                "mantenha-o pendente até classificação tributária e conversão cambial validadas"
            )
        result = self._money(payload.get("realized_result_brl"), "realized_result_brl")
        reference = str(payload.get("reference") or "").strip()
        if not reference:
            raise ValueError("reference é obrigatório para rastreabilidade")
        occurred_on = str(payload.get("occurred_on") or datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat())
        try:
            parsed_date = datetime.strptime(occurred_on, "%Y-%m-%d").date()
            if parsed_date.isoformat() != occurred_on:
                raise ValueError
        except ValueError as exc:
            raise ValueError("occurred_on deve usar YYYY-MM-DD") from exc
        notes = str(payload.get("notes") or "").strip()[:1000]
        with self._connect() as db:
            # Serialize writers before checking the idempotency key. The unique
            # index remains the final guard if multiple workers race.
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT entry_id FROM fiscal_reserve_entries WHERE category = ? AND reference = ?",
                (category, reference),
            ).fetchone()
            if existing is not None:
                raise ValueError("esta referência já foi registrada nesta categoria")
            row = db.execute(
                "SELECT rate FROM fiscal_reserve_settings WHERE category = ?",
                (category,),
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
                (entry_id, category, entry_type, realized_result_brl, reserve_rate,
                 reserve_amount_brl, reference, occurred_on, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(asdict(entry).values()),
            )
        return asdict(entry)

    def summary(
        self,
        as_of: date | None = None,
        history_limit: int = 100,
        history_offset: int = 0,
    ) -> dict[str, Any]:
        if isinstance(history_limit, bool) or not isinstance(history_limit, int) or not 1 <= history_limit <= 500:
            raise ValueError("history_limit deve estar entre 1 e 500")
        if isinstance(history_offset, bool) or not isinstance(history_offset, int) or history_offset < 0:
            raise ValueError("history_offset deve ser um inteiro não negativo")
        rates = self.settings()
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
                    WHERE category = 'BR_DAY_TRADE'
                    AND occurred_on >= ? AND occurred_on < ?""",
                    (start_day.isoformat(), date.fromordinal(end_day.toordinal() + 1).isoformat()),
                ).fetchone()
                period_totals[period_name] = {
                    "start": start_day.isoformat(),
                    "end": end_day.isoformat(),
                    "entries": int(row["count"]),
                    "realized_result_brl": round(float(row["realized_result_brl"]), 2),
                    "reserve_amount_brl": round(float(row["reserve_amount_brl"]), 2),
                }
            for category in sorted(VALID_CATEGORIES):
                row = db.execute(
                    """SELECT COUNT(*) AS count,
                    COALESCE(SUM(realized_result_brl), 0) AS realized_result_brl,
                    COALESCE(SUM(reserve_amount_brl), 0) AS reserve_amount_brl
                    FROM fiscal_reserve_entries WHERE category = ?""",
                    (category,),
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
                    categories[category] = {
                        "rate": rates[category],
                        "entries": int(row["count"]),
                        "realized_result_brl": round(float(row["realized_result_brl"]), 2),
                        "reserve_amount_brl": round(float(row["reserve_amount_brl"]), 2),
                    }
            total = db.execute(
                "SELECT COALESCE(SUM(reserve_amount_brl), 0) AS total FROM fiscal_reserve_entries WHERE category = 'BR_DAY_TRADE'"
            ).fetchone()
            history_total = int(db.execute(
                "SELECT COUNT(*) AS total FROM fiscal_reserve_entries"
            ).fetchone()["total"])
            history = db.execute(
                """SELECT * FROM fiscal_reserve_entries
                ORDER BY occurred_on DESC, created_at DESC, entry_id DESC
                LIMIT ? OFFSET ?""",
                (history_limit, history_offset),
            ).fetchall()
        return {
            "name": "Reserva Fiscal",
            "currency": "BRL",
            "categories": categories,
            "total_reserved_brl": round(float(total["total"]), 2),
            "periods": period_totals,
            "as_of": reference_day.isoformat(),
            "history": [dict(item) for item in history],
            "history_page": {
                "limit": history_limit,
                "offset": history_offset,
                "returned": len(history),
                "total": history_total,
                "has_more": history_offset + len(history) < history_total,
            },
            "limitations": [
                "Estimativa de planejamento; não representa imposto apurado ou devido.",
                "Resultados negativos são registrados, mas compensações fiscais não são calculadas.",
                "Resultados estrangeiros, inclusive registros legados, ficam fora dos totais até classificação tributária validada e conversão para BRL.",
                "Nenhum valor é transferido ou movimentado pela Reserva Fiscal.",
            ],
        }
