from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


class LatestMarketAnalysisStore:
    """Durable, read-only cache of the most recent market-analysis snapshots."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database).expanduser().resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS latest_market_analysis (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    PRIMARY KEY (symbol, timeframe)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_latest_market_analysis_updated "
                "ON latest_market_analysis(updated_at DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database), timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def save(self, symbol: str, timeframe: str, payload: dict[str, Any]) -> None:
        normalized_symbol = str(symbol).strip().upper()
        normalized_timeframe = str(timeframe).strip().lower()
        if not normalized_symbol or not normalized_timeframe:
            raise ValueError("symbol e timeframe são obrigatórios")
        if not isinstance(payload, dict):
            raise ValueError("snapshot deve ser um objeto")
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        updated_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO latest_market_analysis(symbol, timeframe, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (normalized_symbol, normalized_timeframe, serialized, updated_at),
            )

    def latest(self, symbol: str | None = None, timeframe: str | None = None) -> dict[str, Any] | None:
        if bool(symbol) != bool(timeframe):
            raise ValueError("symbol e timeframe devem ser informados juntos")
        with self._lock, self._connect() as connection:
            if symbol and timeframe:
                row = connection.execute(
                    "SELECT payload_json FROM latest_market_analysis WHERE symbol = ? AND timeframe = ?",
                    (str(symbol).strip().upper(), str(timeframe).strip().lower()),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload_json FROM latest_market_analysis "
                    "ORDER BY updated_at DESC, rowid DESC LIMIT 1"
                ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        return payload if isinstance(payload, dict) else None
