from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.models import Candle


class MT5RelayError(ValueError):
    pass


class MT5RelayStore:
    """Durable, bounded inbox for DEMO-only candles pushed by a local MT5 agent."""

    MAX_CANDLES = 500
    SYMBOL_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
    TIMEFRAME_RE = re.compile(r"^(M[1-9][0-9]?|H[1-9][0-9]?|D[1-9][0-9]?|W[1-4])$", re.I)

    def __init__(self, database_path: str | Path, expected_source_id: str) -> None:
        if not isinstance(expected_source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", expected_source_id):
            raise ValueError("expected_source_id válido é obrigatório para vincular o relay")
        self.expected_source_id = expected_source_id
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS mt5_relay_candles (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    PRIMARY KEY(symbol, timeframe, timestamp)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS mt5_relay_messages (
                    message_id TEXT PRIMARY KEY,
                    accepted_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS mt5_relay_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    account_mode TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    source_id TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @classmethod
    def validate_symbol_timeframe(cls, symbol: Any, timeframe: Any) -> tuple[str, str]:
        if not isinstance(symbol, str) or not cls.SYMBOL_RE.fullmatch(symbol.strip()):
            raise MT5RelayError("símbolo inválido")
        if not isinstance(timeframe, str) or not cls.TIMEFRAME_RE.fullmatch(timeframe.strip()):
            raise MT5RelayError("timeframe MT5 inválido")
        return symbol.strip().upper(), timeframe.strip().upper()

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise MT5RelayError("payload deve ser objeto")
        symbol, timeframe = self.validate_symbol_timeframe(
            payload.get("symbol"), payload.get("timeframe")
        )
        if payload.get("account_mode") != "DEMO":
            raise MT5RelayError("ponte aceita somente conta DEMO confirmada")
        message_id = payload.get("message_id")
        if not isinstance(message_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", message_id):
            raise MT5RelayError("message_id UUID obrigatório")
        sent_at_raw = payload.get("sent_at")
        try:
            sent_at = datetime.fromisoformat(str(sent_at_raw).replace("Z", "+00:00"))
            if sent_at.tzinfo is None:
                raise ValueError("timestamp sem fuso")
            age = (datetime.now(timezone.utc) - sent_at.astimezone(timezone.utc)).total_seconds()
            if age < -10 or age > 30:
                raise ValueError("mensagem fora da janela de validade")
        except (TypeError, ValueError) as exc:
            raise MT5RelayError("sent_at inválido ou expirado") from exc
        source_id = payload.get("source_id", "mt5-local")
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", source_id):
            raise MT5RelayError("source_id inválido")
        if source_id != self.expected_source_id:
            raise MT5RelayError("origem não corresponde à origem provisionada neste relay")
        raw_candles = payload.get("candles")
        if not isinstance(raw_candles, list) or not raw_candles or len(raw_candles) > self.MAX_CANDLES:
            raise MT5RelayError(f"candles deve conter entre 1 e {self.MAX_CANDLES} registros")
        parsed: list[Candle] = []
        for item in raw_candles:
            if not isinstance(item, dict):
                raise MT5RelayError("cada candle deve ser objeto")
            try:
                timestamp = datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError("timestamp sem fuso")
                candle = Candle(
                    timestamp=timestamp.astimezone(timezone.utc),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item.get("volume", 0)),
                )
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise MT5RelayError("formato de candle inválido") from exc
            if not candle.is_valid():
                raise MT5RelayError("candle inválido")
            parsed.append(candle)
        parsed.sort(key=lambda candle: candle.timestamp)
        if len({c.timestamp for c in parsed}) != len(parsed):
            raise MT5RelayError("candles duplicados no mesmo lote")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            # One relay database is permanently bound to its first source.
            # Never let a bearer-token holder switch accounts by changing an
            # untrusted payload field; separate accounts need separate stores.
            if db.execute("SELECT 1 FROM mt5_relay_messages WHERE message_id=?", (message_id,)).fetchone():
                raise MT5RelayError("mensagem repetida")
            previous = db.execute(
                "SELECT source_id FROM mt5_relay_state WHERE singleton=1"
            ).fetchone()
            if previous is not None and previous["source_id"] != source_id:
                raise MT5RelayError("origem diferente da origem vinculada a este relay")
            db.execute(
                "INSERT INTO mt5_relay_messages(message_id,accepted_at) VALUES(?,?)",
                (message_id, now),
            )
            for candle in parsed:
                db.execute(
                    """INSERT INTO mt5_relay_candles
                    (symbol,timeframe,timestamp,open,high,low,close,volume)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(symbol,timeframe,timestamp) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume""",
                    (symbol, timeframe, candle.timestamp.isoformat(), candle.open,
                     candle.high, candle.low, candle.close, candle.volume),
                )
            db.execute(
                """INSERT INTO mt5_relay_state(singleton,account_mode,last_seen,source_id)
                VALUES(1,'DEMO',?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                account_mode='DEMO', last_seen=excluded.last_seen, source_id=excluded.source_id""",
                (now, source_id),
            )
            db.execute(
                """DELETE FROM mt5_relay_messages WHERE rowid NOT IN (
                    SELECT rowid FROM mt5_relay_messages ORDER BY accepted_at DESC LIMIT 10000
                )"""
            )
            db.execute(
                """DELETE FROM mt5_relay_candles WHERE rowid IN (
                    SELECT rowid FROM mt5_relay_candles
                    WHERE symbol=? AND timeframe=?
                    ORDER BY timestamp DESC LIMIT -1 OFFSET 1000
                )""",
                (symbol, timeframe),
            )
        return {"accepted": len(parsed), "symbol": symbol, "timeframe": timeframe, "account_mode": "DEMO"}

    def fetch(self, request) -> tuple[Candle, ...]:
        symbol, timeframe = self.validate_symbol_timeframe(request.symbol, request.timeframe)
        with self._connect() as db:
            rows = db.execute(
                """SELECT timestamp,open,high,low,close,volume FROM mt5_relay_candles
                WHERE symbol=? AND timeframe=? ORDER BY timestamp DESC LIMIT ?""",
                (symbol, timeframe, min(int(request.limit), 1000)),
            ).fetchall()
        candles = [
            Candle(datetime.fromisoformat(row["timestamp"]), row["open"], row["high"],
                   row["low"], row["close"], row["volume"])
            for row in reversed(rows)
        ]
        if not candles:
            raise MT5RelayError("ponte ainda não enviou candles para este ativo/período")
        return tuple(candles)

    def get_account_mode(self) -> str:
        with self._connect() as db:
            row = db.execute("SELECT account_mode,last_seen FROM mt5_relay_state WHERE singleton=1").fetchone()
        if row is None:
            raise MT5RelayError("ponte MT5 ainda não enviou heartbeat")
        seen = datetime.fromisoformat(row["last_seen"])
        age = (datetime.now(timezone.utc) - seen).total_seconds()
        if age < 0 or age > 30 or row["account_mode"] != "DEMO":
            raise MT5RelayError("ponte MT5 sem heartbeat DEMO recente")
        return "DEMO"

    def status(self) -> dict[str, Any]:
        try:
            mode = self.get_account_mode()
            connected = True
        except MT5RelayError:
            mode, connected = None, False
        with self._connect() as db:
            count = db.execute("SELECT COUNT(*) FROM mt5_relay_candles").fetchone()[0]
            state = db.execute("SELECT last_seen,source_id FROM mt5_relay_state WHERE singleton=1").fetchone()
        return {
            "connected": connected,
            "account_mode": mode,
            "last_seen": state["last_seen"] if state else None,
            "source_id": state["source_id"] if state else None,
            "stored_candles": int(count),
            "read_only": True,
            "execution_authorized": False,
        }
