"""Tenant/account-isolated candle-close analysis subscriptions.

Each watch is scoped by tenant, subject, provider connection, symbol and
canonical timeframe. Adapters are resolved at execution time and never shared
between account sessions. The worker performs analysis only.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from data.timeframes import get_timeframe_interval, normalize_timeframe
from security.tenant_context import TenantContext


_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
_CONNECTION = re.compile(r"^[a-f0-9]{32}$")


class TenantConnectionTimeframeMonitor:
    MAX_ACTIVE_PER_CONNECTION = 100

    def __init__(
        self,
        path: str | Path,
        session_registry: Any,
        analyzer_factory: Callable[[Any, TenantContext], Any],
        *,
        on_result: Callable[[dict[str, Any]], None] | None = None,
        poll_interval_seconds: float = 2.0,
        close_grace_seconds: float = 3.0,
        max_workers: int = 8,
    ) -> None:
        if session_registry is None or not callable(getattr(session_registry, "get", None)):
            raise ValueError("tenant market-data session registry is required")
        if not callable(analyzer_factory):
            raise ValueError("analyzer_factory must be callable")
        if poll_interval_seconds <= 0 or close_grace_seconds < 0:
            raise ValueError("invalid monitor timing")
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= 32:
            raise ValueError("max_workers deve ser inteiro entre 1 e 32")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_registry = session_registry
        self.analyzer_factory = analyzer_factory
        self.on_result = on_result
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.close_grace_seconds = float(close_grace_seconds)
        self.max_workers = max_workers
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_error: str | None = None
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _initialize(self):
        with self._lock, self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_connection_timeframe_watch (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_processed_candle TEXT,
                    last_signal TEXT,
                    last_status TEXT NOT NULL DEFAULT 'WAITING',
                    last_error TEXT,
                    PRIMARY KEY(tenant_id, subject_id, connection_id, symbol, timeframe)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_connection_timeframe_results (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    candle_at TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    recorded_at REAL NOT NULL,
                    PRIMARY KEY(tenant_id, subject_id, connection_id, symbol, timeframe, candle_at)
                )
            """)

    @staticmethod
    def _owner(context: TenantContext | None) -> TenantContext:
        if not isinstance(context, TenantContext):
            raise PermissionError("trusted tenant context is required")
        return context

    @staticmethod
    def _connection(value: str) -> str:
        if not isinstance(value, str) or not _CONNECTION.fullmatch(value):
            raise ValueError("connection_id inválido")
        return value

    @staticmethod
    def _symbol(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("symbol deve ser texto")
        result = value.strip().upper()
        if not _SYMBOL.fullmatch(result):
            raise ValueError("symbol inválido")
        return result

    def subscribe(self, context: TenantContext, connection_id: str, symbol: str, timeframe: str) -> dict[str, Any]:
        owner = self._owner(context)
        connection = self._connection(connection_id)
        normalized_symbol = self._symbol(symbol)
        normalized_timeframe = normalize_timeframe(timeframe)
        session = self.session_registry.get(owner, connection_id=connection)
        if session is None:
            raise PermissionError("conexão sem adaptador ativo para esta identidade")
        with self._lock, self._connect() as db:
            count = db.execute("""
                SELECT COUNT(*) FROM tenant_connection_timeframe_watch
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND enabled=1
            """, (owner.tenant_id, owner.subject_id, connection)).fetchone()[0]
            existing = db.execute("""
                SELECT enabled FROM tenant_connection_timeframe_watch
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
            """, (owner.tenant_id, owner.subject_id, connection, normalized_symbol, normalized_timeframe)).fetchone()
            if (existing is None or not existing["enabled"]) and count >= self.MAX_ACTIVE_PER_CONNECTION:
                raise ValueError("limite de 100 assinaturas ativas por conta atingido")
            db.execute("""
                INSERT INTO tenant_connection_timeframe_watch
                (tenant_id, subject_id, connection_id, symbol, timeframe, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(tenant_id, subject_id, connection_id, symbol, timeframe)
                DO UPDATE SET enabled=1, last_error=NULL
            """, (owner.tenant_id, owner.subject_id, connection, normalized_symbol, normalized_timeframe, time.time()))
        return {
            "connection_id": connection,
            "provider_id": session.provider_id,
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "enabled": True,
            "execution_authorized": False,
        }

    def unsubscribe(self, context: TenantContext, connection_id: str, symbol: str, timeframe: str) -> bool:
        owner = self._owner(context)
        connection = self._connection(connection_id)
        normalized_symbol = self._symbol(symbol)
        normalized_timeframe = normalize_timeframe(timeframe)
        with self._lock, self._connect() as db:
            cursor = db.execute("""
                UPDATE tenant_connection_timeframe_watch SET enabled=0
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=? AND enabled=1
            """, (owner.tenant_id, owner.subject_id, connection, normalized_symbol, normalized_timeframe))
        return cursor.rowcount == 1

    def subscriptions(self, context: TenantContext, connection_id: str | None = None) -> list[dict[str, Any]]:
        owner = self._owner(context)
        args: list[Any] = [owner.tenant_id, owner.subject_id]
        sql = """
            SELECT connection_id, symbol, timeframe, enabled, last_processed_candle,
                   last_signal, last_status, last_error
            FROM tenant_connection_timeframe_watch
            WHERE tenant_id=? AND subject_id=?
        """
        if connection_id is not None:
            sql += " AND connection_id=?"
            args.append(self._connection(connection_id))
        sql += " ORDER BY connection_id, symbol, timeframe"
        with self._lock, self._connect() as db:
            rows = db.execute(sql, args).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            session = self.session_registry.get(owner, connection_id=item["connection_id"])
            item["provider_id"] = session.provider_id if session else None
            item["adapter_status"] = "BOUND" if session else "NOT_BOUND"
            item["enabled"] = bool(item["enabled"])
            output.append(item)
        return output

    def latest_results(self, context: TenantContext, connection_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        owner = self._owner(context)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit deve ser inteiro de 1 a 200")
        args: list[Any] = [owner.tenant_id, owner.subject_id]
        sql = """
            SELECT connection_id, symbol, timeframe, candle_at, result_json, recorded_at
            FROM tenant_connection_timeframe_results
            WHERE tenant_id=? AND subject_id=?
        """
        if connection_id is not None:
            sql += " AND connection_id=?"
            args.append(self._connection(connection_id))
        sql += " ORDER BY recorded_at DESC LIMIT ?"
        args.append(limit)
        with self._lock, self._connect() as db:
            rows = db.execute(sql, args).fetchall()
        return [{**dict(row), "result": json.loads(row["result_json"])} for row in rows]

    @staticmethod
    def _bucket_start(now: datetime, interval: int) -> datetime:
        epoch = int(now.timestamp())
        if interval % 604800 == 0:
            offset = 3 * 86400
            bucket = ((epoch + offset) // interval) * interval - offset
        else:
            bucket = (epoch // interval) * interval
        return datetime.fromtimestamp(bucket, tz=timezone.utc)

    def expected_last_closed_candle(self, timeframe: str, now: datetime) -> datetime:
        if now.tzinfo is None:
            raise ValueError("now deve conter fuso horário")
        interval = int(get_timeframe_interval(normalize_timeframe(timeframe)).total_seconds())
        eligible = now.astimezone(timezone.utc) - timedelta(seconds=self.close_grace_seconds)
        return self._bucket_start(eligible, interval) - timedelta(seconds=interval)

    def _enabled(self, row: dict[str, Any]) -> bool:
        with self._lock, self._connect() as db:
            result = db.execute("""
                SELECT enabled FROM tenant_connection_timeframe_watch
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
            """, (row["tenant_id"], row["subject_id"], row["connection_id"], row["symbol"], row["timeframe"])).fetchone()
        return bool(result and result["enabled"])

    def _process(self, row: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        owner = TenantContext(row["tenant_id"], row["subject_id"])
        connection = row["connection_id"]
        symbol, timeframe = row["symbol"], row["timeframe"]
        expected = self.expected_last_closed_candle(timeframe, now)
        if row["last_processed_candle"] == expected.isoformat() or not self._enabled(row):
            return None
        try:
            session = self.session_registry.get(owner, connection_id=connection)
            if session is None:
                raise RuntimeError("adapter da conta desconectado ou não vinculado")
            analyzer = self.analyzer_factory(session, owner)
            result = analyzer.analyze(
                symbol=symbol, timeframe=timeframe, limit=120,
                confirmed=True, filters_ok=True, decision_context=owner,
            )
            last_candle = result.get("market_data", {}).get("last_candle_at")
            if not isinstance(last_candle, str):
                raise ValueError("analisador não informou o candle mais recente")
            parsed = datetime.fromisoformat(last_candle.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.astimezone(timezone.utc) != expected:
                with self._lock, self._connect() as db:
                    db.execute("""
                        UPDATE tenant_connection_timeframe_watch
                        SET last_status='WAITING_FOR_CLOSED_CANDLE', last_error=NULL
                        WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
                    """, (owner.tenant_id, owner.subject_id, connection, symbol, timeframe))
                return None
            if not self._enabled(row):
                return None
            signal = str(result.get("signal", "AGUARDAR"))
            enriched = {
                "tenant_context": owner, "connection_id": connection,
                "provider_id": session.provider_id, "source": session.source,
                "symbol": symbol, "timeframe": timeframe,
                "candle_at": expected.isoformat(),
                "previous_signal": row.get("last_signal"), "result": result,
            }
            if self.on_result is not None:
                self.on_result(enriched)
            serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
            with self._lock, self._connect() as db:
                db.execute("""
                    INSERT OR IGNORE INTO tenant_connection_timeframe_results
                    (tenant_id, subject_id, connection_id, symbol, timeframe, candle_at, result_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (owner.tenant_id, owner.subject_id, connection, symbol, timeframe, expected.isoformat(), serialized, time.time()))
                db.execute("""
                    UPDATE tenant_connection_timeframe_watch
                    SET last_processed_candle=?, last_signal=?, last_status=?, last_error=NULL
                    WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
                """, (expected.isoformat(), signal, str(result.get("status", "ANALYZED")), owner.tenant_id, owner.subject_id, connection, symbol, timeframe))
            return enriched
        except Exception as exc:
            with self._lock, self._connect() as db:
                db.execute("""
                    UPDATE tenant_connection_timeframe_watch SET last_status='DATA_UNAVAILABLE', last_error=?
                    WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
                """, (str(exc)[:500], owner.tenant_id, owner.subject_id, connection, symbol, timeframe))
            return None

    def run_once(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now deve conter fuso horário")
        with self._lock, self._connect() as db:
            rows = [dict(row) for row in db.execute("""
                SELECT tenant_id, subject_id, connection_id, symbol, timeframe,
                       last_processed_candle, last_signal
                FROM tenant_connection_timeframe_watch WHERE enabled=1
                ORDER BY tenant_id, subject_id, connection_id, symbol, timeframe
            """).fetchall()]
        output = []
        if not rows:
            return output
        # One slow/disconnected provider must not stall every other account.
        # A bounded pool prevents unbounded fan-out when many watches are active.
        with ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(rows)),
            thread_name_prefix="account-market-cycle",
        ) as executor:
            futures = [
                executor.submit(self._process, row, current.astimezone(timezone.utc))
                for row in rows
            ]
            for future in as_completed(futures):
                item = future.result()
                if item is not None:
                    output.append(item)
        return output

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="tenant-account-timeframe-monitor", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
                self._worker_error = None
            except Exception as exc:
                self._worker_error = type(exc).__name__
            self._stop.wait(self.poll_interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))
            if not thread.is_alive():
                self._thread = None

    def status(self, context: TenantContext | None = None) -> dict[str, Any]:
        if context is None:
            with self._lock, self._connect() as db:
                enabled = db.execute("SELECT COUNT(*) FROM tenant_connection_timeframe_watch WHERE enabled=1").fetchone()[0]
                total = db.execute("SELECT COUNT(*) FROM tenant_connection_timeframe_watch").fetchone()[0]
        else:
            rows = self.subscriptions(context)
            enabled = sum(1 for item in rows if item["enabled"])
            total = len(rows)
        return {
            "enabled": enabled, "total": total,
            "worker_running": bool(self._thread is not None and self._thread.is_alive()),
            "poll_interval_seconds": self.poll_interval_seconds,
            "close_grace_seconds": self.close_grace_seconds,
            "max_workers": self.max_workers,
            "worker_error_class": self._worker_error,
            "scope": "TENANT_SUBJECT_CONNECTION",
            "execution_authorized": False,
        }
