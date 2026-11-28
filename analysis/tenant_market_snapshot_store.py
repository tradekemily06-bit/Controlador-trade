"""Immutable tenant-scoped snapshots of broker market data.

This is an audit/replay primitive, not a provider adapter and not proof that a
provider is live or independently trustworthy. Callers must pass snapshots
created inside the authenticated server-side provider boundary.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.p122_broker_market_data import BrokerMarketDataSnapshot
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


def _utc(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _snapshot_payload(snapshot: BrokerMarketDataSnapshot) -> dict[str, Any]:
    if not isinstance(snapshot, BrokerMarketDataSnapshot):
        raise TypeError("snapshot must be BrokerMarketDataSnapshot")
    if not snapshot.candles:
        raise ValueError("snapshot must contain candles")
    symbol = snapshot.symbol.strip().upper() if isinstance(snapshot.symbol, str) else ""
    source = snapshot.source.strip() if isinstance(snapshot.source, str) else ""
    timeframe = snapshot.timeframe.strip().lower() if isinstance(snapshot.timeframe, str) else ""
    if not symbol or not source or not timeframe:
        raise ValueError("snapshot symbol, timeframe and source are required")
    candles = []
    previous = None
    for candle in snapshot.candles:
        if not candle.is_valid():
            raise ValueError("snapshot contains an invalid candle")
        timestamp = _utc(candle.timestamp, "candle.timestamp")
        if previous is not None and timestamp <= previous:
            raise ValueError("snapshot candles must be strictly chronological")
        previous = timestamp
        values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values):
            raise ValueError("snapshot candle values must be finite numbers")
        candles.append({
            "timestamp": timestamp,
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
        })
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
        "received_at": _utc(snapshot.received_at, "received_at"),
        "candles": candles,
    }


class TenantMarketSnapshotStore:
    """Append-only market snapshots partitioned by authenticated tenant/subject."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_market_snapshots (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    first_candle_at TEXT NOT NULL,
                    last_candle_at TEXT NOT NULL,
                    candle_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, subject_id, snapshot_id)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_market_snapshot_lookup
                ON tenant_market_snapshots
                (tenant_id, subject_id, source_id, symbol, timeframe, last_candle_at)
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def record(
        self,
        context: TenantContext,
        *,
        snapshot_id: str,
        source_id: str,
        snapshot: BrokerMarketDataSnapshot,
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        for field, value in (("snapshot_id", snapshot_id), ("source_id", source_id)):
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
                raise ValueError(f"{field} must be non-empty text up to 200 characters")
        payload = _snapshot_payload(snapshot)
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        recorded_at = datetime.now(timezone.utc).isoformat()
        candles = payload["candles"]
        identity = (
            owner.tenant_id, owner.subject_id, snapshot_id.strip(), source_id.strip(),
            payload["symbol"], payload["timeframe"], payload["received_at"],
            candles[0]["timestamp"], candles[-1]["timestamp"], len(candles),
            payload_json, digest, recorded_at,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("""
                SELECT source_id, symbol, timeframe, received_at, first_candle_at,
                       last_candle_at, candle_count, payload_sha256
                FROM tenant_market_snapshots
                WHERE tenant_id=? AND subject_id=? AND snapshot_id=?
            """, (owner.tenant_id, owner.subject_id, snapshot_id.strip())).fetchone()
            if existing is not None:
                expected = (
                    source_id.strip(), payload["symbol"], payload["timeframe"],
                    payload["received_at"], candles[0]["timestamp"],
                    candles[-1]["timestamp"], len(candles), digest,
                )
                actual = tuple(existing[key] for key in (
                    "source_id", "symbol", "timeframe", "received_at",
                    "first_candle_at", "last_candle_at", "candle_count", "payload_sha256",
                ))
                if actual != expected:
                    raise ValueError("snapshot_id already exists with different immutable data")
                return {
                    "snapshot_id": snapshot_id.strip(), "status": "ALREADY_RECORDED",
                    "payload_sha256": digest, "candle_count": len(candles),
                }
            db.execute("""
                INSERT INTO tenant_market_snapshots
                (tenant_id, subject_id, snapshot_id, source_id, symbol, timeframe,
                 received_at, first_candle_at, last_candle_at, candle_count,
                 payload_json, payload_sha256, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, identity)
        return {
            "snapshot_id": snapshot_id.strip(), "status": "RECORDED",
            "payload_sha256": digest, "candle_count": len(candles),
        }

    def get(self, context: TenantContext, snapshot_id: str) -> dict[str, Any] | None:
        owner = require_tenant_context(context)
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError("snapshot_id is required")
        with self._connect() as db:
            row = db.execute("""
                SELECT snapshot_id, source_id, symbol, timeframe, received_at,
                       first_candle_at, last_candle_at, candle_count,
                       payload_json, payload_sha256, recorded_at
                FROM tenant_market_snapshots
                WHERE tenant_id=? AND subject_id=? AND snapshot_id=?
            """, (owner.tenant_id, owner.subject_id, snapshot_id.strip())).fetchone()
        if row is None:
            return None
        payload_json = row["payload_json"]
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if digest != row["payload_sha256"]:
            raise RuntimeError("stored market snapshot checksum mismatch")
        return {
            "snapshot_id": row["snapshot_id"], "source_id": row["source_id"],
            "symbol": row["symbol"], "timeframe": row["timeframe"],
            "received_at": row["received_at"], "first_candle_at": row["first_candle_at"],
            "last_candle_at": row["last_candle_at"], "candle_count": row["candle_count"],
            "payload": json.loads(payload_json), "payload_sha256": digest,
            "recorded_at": row["recorded_at"],
            "provenance_status": "PROVIDER_BOUNDARY_ASSERTED_NOT_INDEPENDENTLY_VERIFIED",
        }
