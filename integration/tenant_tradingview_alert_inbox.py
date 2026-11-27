"""Tenant-scoped TradingView alert webhook inbox.

TradingView webhooks are alert events, not a continuous candle feed. This
service stores validated read-only alert events and never creates orders.
The HTTP edge must authenticate the owner and enforce TLS/rate limits.
"""
from __future__ import annotations

import hmac
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


class TradingViewAlertError(ValueError):
    pass


class TenantTradingViewAlertInbox:
    MAX_PAYLOAD_BYTES = 16_384
    MAX_EVENT_AGE_SECONDS = 300
    _CONNECTION = re.compile(r"^[a-f0-9]{32}$")
    _EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
    _SYMBOL = re.compile(r"^[A-Za-z0-9._:/-]{1,64}$")
    _INTERVAL = re.compile(r"^[A-Za-z0-9]{1,12}$")
    _ACTION = {"BUY", "SELL", "WAIT", "ALERT"}

    def __init__(
        self,
        path: str | Path,
        connections: Any,
        secret_resolver: Callable[[TenantContext, str], str],
        *, on_event=None,
    ) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant provider connection registry is required")
        if not callable(secret_resolver) and not callable(getattr(secret_resolver, "verify", None)):
            raise ValueError("trusted per-connection webhook secret resolver/verifier is required")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connections = connections
        self.secret_resolver = secret_resolver
        if on_event is not None and not callable(on_event):
            raise ValueError("on_event deve ser callable")
        self.on_event = on_event
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_tradingview_alert_events (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    fired_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, subject_id, connection_id, event_id)
                )
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def ingest(
        self,
        context: TenantContext,
        connection_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        if not isinstance(connection_id, str) or not self._CONNECTION.fullmatch(connection_id):
            raise TradingViewAlertError("connection_id inválido")
        if not isinstance(payload, dict):
            raise TradingViewAlertError("payload deve ser objeto JSON")
        try:
            encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TradingViewAlertError("payload JSON inválido") from exc
        if len(encoded) > self.MAX_PAYLOAD_BYTES:
            raise TradingViewAlertError("payload excede 16 KB")

        account = next(
            (item for item in self.connections.list_connections(owner)
             if item["connection_id"] == connection_id),
            None,
        )
        if account is None or account.get("provider_id") != "tradingview_webhook":
            raise PermissionError("webhook não pertence a uma conexão TradingView desta identidade")
        if account.get("status") not in {"PENDING", "CONNECTED"}:
            raise PermissionError("conexão TradingView não está ativa")

        supplied_secret = payload.get("secret")
        verifier = getattr(self.secret_resolver, "verify", None)
        if callable(verifier):
            if not verifier(owner, connection_id, supplied_secret):
                raise PermissionError("segredo do webhook inválido")
        else:
            expected_secret = self.secret_resolver(owner, connection_id)
            if not isinstance(expected_secret, str) or len(expected_secret) < 32:
                raise PermissionError("segredo do webhook não está provisionado")
            if not isinstance(supplied_secret, str) or not hmac.compare_digest(
                supplied_secret, expected_secret
            ):
                raise PermissionError("segredo do webhook inválido")

        event_id = payload.get("event_id")
        ticker = payload.get("ticker")
        interval = payload.get("interval")
        action = payload.get("action")
        if not isinstance(event_id, str) or not self._EVENT_ID.fullmatch(event_id):
            raise TradingViewAlertError("event_id inválido")
        if not isinstance(ticker, str) or not self._SYMBOL.fullmatch(ticker.strip()):
            raise TradingViewAlertError("ticker inválido")
        if not isinstance(interval, str) or not self._INTERVAL.fullmatch(interval.strip()):
            raise TradingViewAlertError("interval inválido")
        if not isinstance(action, str) or action.upper() not in self._ACTION:
            raise TradingViewAlertError("action deve ser BUY, SELL, WAIT ou ALERT")

        try:
            fired = datetime.fromisoformat(
                str(payload.get("fired_at", "")).replace("Z", "+00:00")
            )
            if fired.tzinfo is None:
                raise ValueError("timezone ausente")
            age = (datetime.now(timezone.utc) - fired.astimezone(timezone.utc)).total_seconds()
            if age < -10 or age > self.MAX_EVENT_AGE_SECONDS:
                raise ValueError("evento expirado ou futuro")
        except (TypeError, ValueError) as exc:
            raise TradingViewAlertError("fired_at inválido, sem fuso ou fora da janela") from exc

        price = payload.get("price")
        if price is not None:
            if isinstance(price, bool) or not isinstance(price, (int, float)):
                raise TradingViewAlertError("price deve ser número finito positivo")
            try:
                price = float(price)
            except (OverflowError, ValueError) as exc:
                raise TradingViewAlertError("price deve ser número finito positivo") from exc
            if not math.isfinite(price) or price <= 0:
                raise TradingViewAlertError("price deve ser número finito positivo")

        safe_payload = {
            "event_id": event_id,
            "ticker": ticker.strip(),
            "interval": interval.strip(),
            "action": action.upper(),
            "price": price,
            "fired_at": fired.astimezone(timezone.utc).isoformat(),
        }
        received_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            try:
                db.execute("""
                    INSERT INTO tenant_tradingview_alert_events
                    (tenant_id,subject_id,connection_id,event_id,ticker,interval,action,
                     price,fired_at,received_at,payload_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    owner.tenant_id, owner.subject_id, connection_id, event_id,
                    safe_payload["ticker"], safe_payload["interval"], safe_payload["action"],
                    price, safe_payload["fired_at"], received_at,
                    json.dumps(safe_payload, separators=(",", ":")),
                ))
            except sqlite3.IntegrityError as exc:
                raise TradingViewAlertError("evento repetido") from exc
        self.connections.mark_connected_after_relay_handshake(
            owner, connection_id=connection_id
        )
        if self.on_event is not None:
            try:
                self.on_event(owner, dict(safe_payload, connection_id=connection_id))
            except Exception:
                # The alert is durably accepted even if a downstream notifier is unavailable.
                pass
        return {
            "accepted": True,
            "event_id": event_id,
            "ticker": safe_payload["ticker"],
            "interval": safe_payload["interval"],
            "action": safe_payload["action"],
            "received_at": received_at,
            "read_only": True,
            "execution_authorized": False,
        }

    def list_events(
        self, context: TenantContext, connection_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        owner = require_tenant_context(context)
        if not isinstance(connection_id, str) or not self._CONNECTION.fullmatch(connection_id):
            raise TradingViewAlertError("connection_id inválido")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise TradingViewAlertError("limit deve ser inteiro de 1 a 200")
        with self._connect() as db:
            rows = db.execute("""
                SELECT event_id,ticker,interval,action,price,fired_at,received_at
                FROM tenant_tradingview_alert_events
                WHERE tenant_id=? AND subject_id=? AND connection_id=?
                ORDER BY received_at DESC LIMIT ?
            """, (owner.tenant_id, owner.subject_id, connection_id, limit)).fetchall()
        return [dict(row) for row in rows]
