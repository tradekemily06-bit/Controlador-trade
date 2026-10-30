"""Reserva Fiscal: earmarked planning reserve for realized trading results.

Rates are configurable planning defaults, not a tax calculator or tax advice.
Foreign results require an explicit classification before a rate is applied.
All monetary inputs are stored in BRL; FX conversion must happen upstream and
the original currency/rate should be retained by a future import adapter.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RATES = {
    "BR_DAY_TRADE": 20.0,
    "FOREIGN_FINANCIAL_ASSET": 15.0,
}
VALID_CATEGORIES = frozenset(DEFAULT_RATES)


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
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

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
        if not isinstance(rates, dict) or set(rates) != VALID_CATEGORIES:
            raise ValueError("informe os percentuais de BR_DAY_TRADE e FOREIGN_FINANCIAL_ASSET")
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
        result = self._money(payload.get("realized_result_brl"), "realized_result_brl")
        reference = str(payload.get("reference") or "").strip()
        if not reference:
            raise ValueError("reference é obrigatório para rastreabilidade")
        occurred_on = str(payload.get("occurred_on") or date.today().isoformat())
        try:
            date.fromisoformat(occurred_on)
        except ValueError as exc:
            raise ValueError("occurred_on deve usar YYYY-MM-DD") from exc
        notes = str(payload.get("notes") or "").strip()[:1000]
        with self._connect() as db:
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

    def summary(self) -> dict[str, Any]:
        rates = self.settings()
        categories: dict[str, dict[str, Any]] = {}
        with self._connect() as db:
            for category in sorted(VALID_CATEGORIES):
                row = db.execute(
                    """SELECT COUNT(*) AS count,
                    COALESCE(SUM(realized_result_brl), 0) AS realized_result_brl,
                    COALESCE(SUM(reserve_amount_brl), 0) AS reserve_amount_brl
                    FROM fiscal_reserve_entries WHERE category = ?""",
                    (category,),
                ).fetchone()
                categories[category] = {
                    "rate": rates[category],
                    "entries": int(row["count"]),
                    "realized_result_brl": round(float(row["realized_result_brl"]), 2),
                    "reserve_amount_brl": round(float(row["reserve_amount_brl"]), 2),
                }
            total = db.execute(
                "SELECT COALESCE(SUM(reserve_amount_brl), 0) AS total FROM fiscal_reserve_entries"
            ).fetchone()
            history = db.execute(
                """SELECT * FROM fiscal_reserve_entries
                ORDER BY occurred_on DESC, created_at DESC LIMIT 100"""
            ).fetchall()
        return {
            "name": "Reserva Fiscal",
            "currency": "BRL",
            "categories": categories,
            "total_reserved_brl": round(float(total["total"]), 2),
            "history": [dict(item) for item in history],
            "limitations": [
                "Estimativa de planejamento; não representa imposto apurado ou devido.",
                "Resultados negativos são registrados, mas compensações fiscais não são calculadas.",
                "Resultados estrangeiros exigem classificação tributária validada e conversão para BRL.",
                "Nenhum valor é transferido ou movimentado pela Reserva Fiscal.",
            ],
        }
