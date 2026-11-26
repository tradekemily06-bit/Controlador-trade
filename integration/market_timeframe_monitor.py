from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from data.timeframes import get_timeframe_interval, normalize_timeframe


_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")


class MarketTimeframeMonitor:
    """Persistent subscriptions and candle-close analysis loop.

    The monitor only requests read-only analysis. It stores subscriptions and
    the last processed candle, and never submits orders. A worker runs only
    while the standalone server process is alive.
    """

    def __init__(
        self,
        path: str | Path,
        analyzer: Any,
        on_result: Callable[[dict[str, Any]], None] | None = None,
        *,
        poll_interval_seconds: float = 2.0,
        close_grace_seconds: float = 3.0,
    ) -> None:
        if analyzer is None or not callable(getattr(analyzer, "analyze", None)):
            raise ValueError("analyzer must implement analyze")
        if poll_interval_seconds <= 0 or close_grace_seconds < 0:
            raise ValueError("invalid monitor timing")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.analyzer = analyzer
        self.on_result = on_result
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.close_grace_seconds = float(close_grace_seconds)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_error: str | None = None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS market_timeframe_watch (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_processed_candle TEXT,
                    last_signal TEXT,
                    last_status TEXT NOT NULL DEFAULT 'WAITING',
                    last_error TEXT,
                    PRIMARY KEY(symbol, timeframe)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS market_timeframe_results (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    candle_at TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    recorded_at REAL NOT NULL,
                    PRIMARY KEY(symbol, timeframe, candle_at)
                )
                """
            )

    @staticmethod
    def _validate_symbol(symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("symbol must be text")
        value = symbol.strip().upper()
        if not _SYMBOL.fullmatch(value):
            raise ValueError("symbol inválido")
        return value

    def subscribe(self, symbol: str, timeframe: str, *, now: float | None = None) -> dict[str, Any]:
        normalized_symbol = self._validate_symbol(symbol)
        normalized_timeframe = normalize_timeframe(timeframe)
        current = time.time() if now is None else float(now)
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT enabled FROM market_timeframe_watch WHERE symbol=? AND timeframe=?",
                (normalized_symbol, normalized_timeframe),
            ).fetchone()
            active_count = db.execute(
                "SELECT COUNT(*) FROM market_timeframe_watch WHERE enabled=1"
            ).fetchone()[0]
            if existing is None and active_count >= 100:
                raise ValueError("limite de 100 assinaturas ativas atingido")
            db.execute(
                """
                INSERT INTO market_timeframe_watch(symbol, timeframe, enabled, created_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(symbol, timeframe) DO UPDATE SET enabled=1, last_error=NULL
                """,
                (normalized_symbol, normalized_timeframe, current),
            )
        return {"symbol": normalized_symbol, "timeframe": normalized_timeframe, "enabled": True}

    def unsubscribe(self, symbol: str, timeframe: str) -> bool:
        normalized_symbol = self._validate_symbol(symbol)
        normalized_timeframe = normalize_timeframe(timeframe)
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "UPDATE market_timeframe_watch SET enabled=0 WHERE symbol=? AND timeframe=? AND enabled=1",
                (normalized_symbol, normalized_timeframe),
            )
        return cursor.rowcount == 1

    def subscriptions(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                """
                SELECT symbol, timeframe, enabled, last_processed_candle,
                       last_signal, last_status, last_error
                FROM market_timeframe_watch
                ORDER BY symbol, timeframe
                """
            ).fetchall()
        return [
            {
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "enabled": bool(row["enabled"]),
                "last_processed_candle": row["last_processed_candle"],
                "last_signal": row["last_signal"],
                "status": row["last_status"],
                "last_error": row["last_error"],
            }
            for row in rows
        ]

    def latest_results(self, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer from 1 to 200")
        with self._lock, self._connect() as db:
            rows = db.execute(
                """
                SELECT symbol, timeframe, candle_at, result_json, recorded_at
                FROM market_timeframe_results
                ORDER BY recorded_at DESC, symbol, timeframe
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "candle_at": row["candle_at"],
                "result": json.loads(row["result_json"]),
                "recorded_at": row["recorded_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _bucket_start(now: datetime, interval_seconds: int) -> datetime:
        epoch = int(now.timestamp())
        if interval_seconds % 604800 == 0:
            offset = 3 * 86400  # Monday 00:00 UTC
            bucket = ((epoch + offset) // interval_seconds) * interval_seconds - offset
        else:
            bucket = (epoch // interval_seconds) * interval_seconds
        return datetime.fromtimestamp(bucket, tz=timezone.utc)

    def expected_last_closed_candle(self, timeframe: str, *, now: datetime | None = None) -> datetime:
        normalized = normalize_timeframe(timeframe)
        interval = int(get_timeframe_interval(normalized).total_seconds())
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        eligible = current.astimezone(timezone.utc) - timedelta(seconds=self.close_grace_seconds)
        return self._bucket_start(eligible, interval) - timedelta(seconds=interval)

    def _record_error(self, symbol: str, timeframe: str, error: Exception) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                UPDATE market_timeframe_watch SET last_status='DATA_UNAVAILABLE',
                    last_error=? WHERE symbol=? AND timeframe=?
                """,
                (str(error)[:500], symbol, timeframe),
            )

    def _process(self, subscription: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        symbol = subscription["symbol"]
        timeframe = subscription["timeframe"]
        expected = self.expected_last_closed_candle(timeframe, now=now)
        previous = subscription.get("last_processed_candle")
        if previous == expected.isoformat():
            return None
        try:
            result = self.analyzer.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=120,
                confirmed=True,
                filters_ok=True,
            )
            market_data = result.get("market_data", {})
            last_candle = market_data.get("last_candle_at")
            if not isinstance(last_candle, str):
                raise ValueError("analyzer did not return last_candle_at")
            parsed_last = datetime.fromisoformat(last_candle.replace("Z", "+00:00"))
            if parsed_last.tzinfo is None or parsed_last.astimezone(timezone.utc) != expected:
                with self._lock, self._connect() as db:
                    db.execute(
                        """
                        UPDATE market_timeframe_watch
                        SET last_status='WAITING_FOR_CLOSED_CANDLE', last_error=NULL
                        WHERE symbol=? AND timeframe=?
                        """,
                        (symbol, timeframe),
                    )
                return None

            signal = str(result.get("signal", "AGUARDAR"))
            enriched = {
                "symbol": symbol,
                "timeframe": timeframe,
                "candle_at": expected.isoformat(),
                "previous_signal": subscription.get("last_signal"),
                "result": result,
            }
            # Publish side effects before marking the candle processed. If
            # notification persistence fails, the next poll retries this
            # candle; stable notification IDs make that retry idempotent.
            if self.on_result is not None:
                self.on_result(enriched)
            serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
            with self._lock, self._connect() as db:
                db.execute(
                    """
                    INSERT OR IGNORE INTO market_timeframe_results
                        (symbol, timeframe, candle_at, result_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (symbol, timeframe, expected.isoformat(), serialized, time.time()),
                )
                db.execute(
                    """
                    UPDATE market_timeframe_watch
                    SET last_processed_candle=?, last_signal=?, last_status=?, last_error=NULL
                    WHERE symbol=? AND timeframe=?
                    """,
                    (
                        expected.isoformat(),
                        signal,
                        str(result.get("status", "ANALYZED")),
                        symbol,
                        timeframe,
                    ),
                )
            return enriched
        except Exception as exc:
            self._record_error(symbol, timeframe, exc)
            return None

    def run_once(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        active = [item for item in self.subscriptions() if item["enabled"]]
        processed = []
        for item in active:
            result = self._process(item, current.astimezone(timezone.utc))
            if result is not None:
                processed.append(result)
        return processed

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="controlador-market-timeframe-monitor",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
                self._worker_error = None
            except Exception as exc:
                self._worker_error = str(exc)[:500]
            self._stop.wait(self.poll_interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def status(self) -> dict[str, Any]:
        subscriptions = self.subscriptions()
        return {
            "enabled": sum(1 for item in subscriptions if item["enabled"]),
            "total": len(subscriptions),
            "worker_running": bool(self._thread is not None and self._thread.is_alive()),
            "poll_interval_seconds": self.poll_interval_seconds,
            "close_grace_seconds": self.close_grace_seconds,
            "worker_error": self._worker_error,
            "execution_authorized": False,
            "subscriptions": subscriptions,
        }
