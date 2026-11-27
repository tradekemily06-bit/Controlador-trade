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
        # Push streams are keyed by the full security boundary. The monitor
        # uses them as a closed-candle readiness gate before analysis.
        self._live_streams: set[tuple[str, str, str, str, str]] = set()
        self._live_stream_adapters: dict[tuple[str, str, str, str, str], Any] = {}
        self._live_candles: dict[tuple[str, str, str, str, str], Any] = {}
        self._live_stream_retry_at: dict[tuple[str, str, str, str, str], float] = {}
        self._processing: set[tuple[str, str, str, str, str]] = set()
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

    def _ensure_live_stream(
        self, owner: TenantContext, session: Any, connection: str,
        symbol: str, timeframe: str,
    ) -> bool:
        adapter = getattr(session, "adapter", None)
        subscribe = getattr(adapter, "subscribe_live_candles", None)
        if not callable(subscribe):
            return False
        key = (owner.tenant_id, owner.subject_id, connection, symbol, timeframe)
        previous_adapter = None
        with self._lock:
            currently_bound = key in self._live_streams and self._live_stream_adapters.get(key) is adapter
        if currently_bound:
            health = getattr(adapter, "status", None)
            healthy = True
            if callable(health):
                try:
                    reported = health()
                    healthy = not isinstance(reported, dict) or reported.get("connected") is not False
                except Exception:
                    healthy = False
            if healthy:
                return True
        with self._lock:
            if key in self._live_streams:
                self._live_streams.discard(key)
                previous_adapter = self._live_stream_adapters.pop(key, None)
                self._live_candles.pop(key, None)
                self._live_stream_retry_at.pop(key, None)
            if self._live_stream_retry_at.get(key, 0.0) > time.monotonic():
                return False
        if previous_adapter is not None:
            previous_unsubscribe = getattr(previous_adapter, "unsubscribe_live_candles", None)
            if callable(previous_unsubscribe):
                try:
                    previous_unsubscribe(symbol, timeframe)
                except Exception:
                    pass
        health = getattr(adapter, "status", None)
        if callable(health):
            try:
                reported = health()
                if isinstance(reported, dict) and reported.get("connected") is False:
                    reconnect = getattr(adapter, "reconnect", None)
                    if not callable(reconnect):
                        raise RuntimeError("provider disconnected and does not support safe reconnect")
                    reconnect()
            except Exception:
                with self._lock:
                    self._live_stream_retry_at[key] = time.monotonic() + 10.0
                return False
        def receive(event: Any) -> None:
            if not isinstance(event, dict) or event.get("closed") is not True:
                return
            if str(event.get("symbol", "")).strip().upper() != symbol:
                return
            if str(event.get("timeframe", "")).strip().lower() != timeframe:
                return
            event_account = event.get("account_id")
            adapter_account = getattr(adapter, "account_id", None)
            if adapter_account is not None and event_account != adapter_account:
                return
            candle = event.get("candle")
            timestamp = getattr(candle, "timestamp", None)
            if timestamp is None or timestamp.tzinfo is None:
                return
            valid = getattr(candle, "is_valid", None)
            if not callable(valid) or not valid():
                return
            with self._lock:
                # A callback retained by an old adapter may fire after account
                # rebind/disconnect. Accept events only from the currently
                # registered adapter for this exact tenant/account watch.
                if key not in self._live_streams or self._live_stream_adapters.get(key) is not adapter:
                    return
                previous = self._live_candles.get(key)
                previous_at = getattr(previous, "timestamp", None)
                if previous_at is None or timestamp.astimezone(timezone.utc) >= previous_at.astimezone(timezone.utc):
                    self._live_candles[key] = candle
        # Reserve the callback identity before subscribing so synchronous
        # first events are not lost; roll back atomically if provider rejects.
        with self._lock:
            self._live_streams.add(key)
            self._live_stream_adapters[key] = adapter
            self._live_candles.pop(key, None)
        try:
            subscribe(symbol, timeframe, receive)
        except Exception:
            with self._lock:
                if self._live_stream_adapters.get(key) is adapter:
                    self._live_streams.discard(key)
                    self._live_stream_adapters.pop(key, None)
                    self._live_candles.pop(key, None)
                self._live_stream_retry_at[key] = time.monotonic() + 10.0
            return False
        with self._lock:
            self._live_stream_retry_at.pop(key, None)
        return True

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
        live_stream = self._ensure_live_stream(
            owner, session, connection, normalized_symbol, normalized_timeframe
        )
        return {
            "connection_id": connection,
            "provider_id": session.provider_id,
            "live_candle_stream": "BOUND" if live_stream else "NOT_SUPPORTED_OR_UNAVAILABLE",
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
        if cursor.rowcount == 1:
            key = (owner.tenant_id, owner.subject_id, connection, normalized_symbol, normalized_timeframe)
            with self._lock:
                self._live_streams.discard(key)
                previous_adapter = self._live_stream_adapters.pop(key, None)
                self._live_candles.pop(key, None)
                self._live_stream_retry_at.pop(key, None)
            session = self.session_registry.get(owner, connection_id=connection)
            adapter = previous_adapter or (getattr(session, "adapter", None) if session else None)
            unsubscribe = getattr(adapter, "unsubscribe_live_candles", None)
            if callable(unsubscribe):
                try:
                    unsubscribe(normalized_symbol, normalized_timeframe)
                except Exception:
                    pass
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
            adapter = getattr(session, "adapter", None) if session else None
            adapter_health = getattr(adapter, "status", None)
            try:
                health = adapter_health() if callable(adapter_health) else {}
            except Exception:
                health = {"connected": False}
            connected = bool(session) and not (isinstance(health, dict) and health.get("connected") is False)
            item["adapter_status"] = "CONNECTED" if connected else "DISCONNECTED"
            key = (owner.tenant_id, owner.subject_id, item["connection_id"], item["symbol"], item["timeframe"])
            with self._lock:
                stream_bound = key in self._live_streams
                candle = self._live_candles.get(key)
            candle_at = getattr(candle, "timestamp", None)
            item["last_live_candle_at"] = candle_at.isoformat() if candle_at is not None else None
            now = datetime.now(timezone.utc)
            expected = self.expected_last_closed_candle(item["timeframe"], now)
            item["expected_last_closed_candle_at"] = expected.isoformat()
            if candle_at is not None and candle_at.tzinfo is not None:
                age = (now - candle_at.astimezone(timezone.utc)).total_seconds()
                item["live_candle_age_seconds"] = round(age, 3)
            else:
                age = None
                item["live_candle_age_seconds"] = None
            if not connected:
                item["live_stream_status"] = "DISCONNECTED"
                item["data_freshness_state"] = "DISCONNECTED"
            elif not stream_bound:
                item["live_stream_status"] = "NOT_SUPPORTED_OR_UNAVAILABLE"
                processed = item.get("last_processed_candle")
                if not processed:
                    item["data_freshness_state"] = "WAITING_FOR_CANDLE"
                else:
                    try:
                        processed_at = datetime.fromisoformat(processed.replace("Z", "+00:00"))
                        if processed_at.tzinfo is None or processed_at.astimezone(timezone.utc) < expected:
                            item["data_freshness_state"] = "STALE"
                        elif processed_at.astimezone(timezone.utc) > expected:
                            item["data_freshness_state"] = "INVALID"
                        else:
                            item["data_freshness_state"] = "FRESH"
                    except (TypeError, ValueError):
                        item["data_freshness_state"] = "INVALID"
            elif candle_at is None:
                item["live_stream_status"] = "BOUND_WAITING_FOR_CANDLE"
                item["data_freshness_state"] = "WAITING_FOR_CANDLE"
            elif candle_at.tzinfo is None:
                item["live_stream_status"] = "INVALID_TIMESTAMP"
                item["data_freshness_state"] = "INVALID"
            else:
                freshness_limit = get_timeframe_interval(item["timeframe"]).total_seconds() + self.close_grace_seconds + self.poll_interval_seconds
                if age < -5:
                    state = "INVALID"
                elif candle_at.astimezone(timezone.utc) == expected:
                    state = "FRESH"
                elif age > freshness_limit or candle_at.astimezone(timezone.utc) < expected:
                    state = "STALE"
                else:
                    state = "WAITING_FOR_CLOSE"
                item["live_stream_status"] = state
                item["data_freshness_state"] = state
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
        owner_key = (
            row["tenant_id"], row["subject_id"], row["connection_id"],
            row["symbol"], row["timeframe"],
        )
        with self._lock:
            if owner_key in self._processing:
                return None
            self._processing.add(owner_key)
        try:
            return self._process_claimed(row, now)
        finally:
            with self._lock:
                self._processing.discard(owner_key)

    def _process_claimed(self, row: dict[str, Any], now: datetime) -> dict[str, Any] | None:
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
            stream_key = (owner.tenant_id, owner.subject_id, connection, symbol, timeframe)
            # Rebind persisted watches after process restart or a transient adapter
            # rebind; retry is throttled so a broken provider is not hammered.
            stream_capable = callable(getattr(getattr(session, "adapter", None), "subscribe_live_candles", None))
            stream_ready = self._ensure_live_stream(owner, session, connection, symbol, timeframe)
            with self._lock:
                stream_bound = stream_key in self._live_streams
                stream_candle = self._live_candles.get(stream_key)
            if stream_capable and not stream_ready:
                with self._lock, self._connect() as db:
                    db.execute("""
                        UPDATE tenant_connection_timeframe_watch
                        SET last_status='LIVE_STREAM_UNAVAILABLE', last_error=NULL
                        WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
                    """, (owner.tenant_id, owner.subject_id, connection, symbol, timeframe))
                return None
            if stream_bound:
                stream_at = getattr(stream_candle, "timestamp", None)
                if stream_at is None or stream_at.tzinfo is None or stream_at.astimezone(timezone.utc) != expected:
                    with self._lock, self._connect() as db:
                        db.execute("""
                            UPDATE tenant_connection_timeframe_watch
                            SET last_status='WAITING_FOR_LIVE_CLOSED_CANDLE', last_error=NULL
                            WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
                        """, (owner.tenant_id, owner.subject_id, connection, symbol, timeframe))
                    return None
            analyzer = self.analyzer_factory(session, owner)
            analysis_kwargs = {
                "symbol": symbol, "timeframe": timeframe, "limit": 120,
                "confirmed": True, "filters_ok": True, "decision_context": owner,
            }
            if stream_bound:
                analysis_kwargs["live_candle"] = stream_candle
            result = analyzer.analyze(**analysis_kwargs)
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
            serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
            with self._lock, self._connect() as db:
                inserted = db.execute("""
                    INSERT OR IGNORE INTO tenant_connection_timeframe_results
                    (tenant_id, subject_id, connection_id, symbol, timeframe, candle_at, result_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (owner.tenant_id, owner.subject_id, connection, symbol, timeframe, expected.isoformat(), serialized, time.time())).rowcount
                db.execute("""
                    UPDATE tenant_connection_timeframe_watch
                    SET last_processed_candle=?, last_signal=?, last_status=?, last_error=NULL
                    WHERE tenant_id=? AND subject_id=? AND connection_id=? AND symbol=? AND timeframe=?
                """, (expected.isoformat(), signal, str(result.get("status", "ANALYZED")), owner.tenant_id, owner.subject_id, connection, symbol, timeframe))
            # A duplicate candle must not fan out duplicate notifications.
            if inserted != 1:
                return None
            # Durable analysis history must not depend on notification delivery.
            # A failing push/webhook sink is isolated from market-data processing.
            if self.on_result is not None:
                try:
                    self.on_result(enriched)
                except Exception:
                    pass
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
        with self._lock:
            if context is None:
                live_streams = len(self._live_streams)
                buffered_live_candles = len(self._live_candles)
                adapter_bindings = len(self._live_stream_adapters)
                worker_error_class = self._worker_error
            else:
                prefix = (context.tenant_id, context.subject_id)
                live_streams = sum(1 for key in self._live_streams if key[:2] == prefix)
                buffered_live_candles = sum(1 for key in self._live_candles if key[:2] == prefix)
                adapter_bindings = sum(1 for key in self._live_stream_adapters if key[:2] == prefix)
                # A tenant must not infer another tenant's provider/worker failure.
                worker_error_class = None
        return {
            "enabled": enabled, "total": total,
            "worker_running": bool(self._thread is not None and self._thread.is_alive()),
            "poll_interval_seconds": self.poll_interval_seconds,
            "close_grace_seconds": self.close_grace_seconds,
            "max_workers": self.max_workers,
            "worker_error_class": worker_error_class,
            "live_streams": live_streams,
            "buffered_live_candles": buffered_live_candles,
            "live_stream_adapter_bindings": adapter_bindings,
            "scope": "TENANT_SUBJECT_CONNECTION" if context is not None else "LOCAL_OPERATOR",
            "execution_authorized": False,
        }
