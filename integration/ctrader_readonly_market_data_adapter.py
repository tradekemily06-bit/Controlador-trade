"""Read-only cTrader Open API market-data adapter.

The adapter normalizes official Open API trendbars into the broker-neutral
Candle model. Network transport is injected so SDK event-loop ownership stays
outside the analysis core. The account must be verified as DEMO.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from data.feed import MarketDataRequest
from data.models import Candle


_CTRADER_PERIODS = {
    "1m": "M1", "5m": "M5", "10m": "M10", "15m": "M15",
    "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D1", "1w": "W1",
}


def _field(value: Any, key: str):
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


class CTraderReadOnlyMarketDataAdapter:
    """Broker-neutral adapter over a host-owned cTrader Open API transport.

    Transport contract:
      connect(), application_auth(), account_details(account_id),
      account_auth(account_id), resolve_symbol(account_id, symbol),
      get_trendbars(account_id, symbol_id, period, count), status(), disconnect().
    """

    def __init__(self, transport: Any, *, account_id: int, source: str = "ctrader_open_api") -> None:
        if transport is None:
            raise ValueError("cTrader transport é obrigatório")
        if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id cTrader inválido")
        self.transport = transport
        self.account_id = account_id
        self.source = source
        self._connected = False
        self._authenticated = False
        self._symbols: dict[str, Any] = {}
        self._request_lock = threading.Lock()
        self._last_historical_request = 0.0

    def connect(self) -> None:
        connect = getattr(self.transport, "connect", None)
        if not callable(connect):
            raise ValueError("transport cTrader deve implementar connect()")
        connect()
        self._connected = True

    def handshake(self) -> dict[str, Any]:
        if not self._connected:
            raise RuntimeError("cTrader transport não conectado")
        app_auth = getattr(self.transport, "application_auth", None)
        account_details = getattr(self.transport, "account_details", None)
        account_auth = getattr(self.transport, "account_auth", None)
        if not all(callable(item) for item in (app_auth, account_details, account_auth)):
            raise ValueError("transport cTrader sem autenticação completa")
        app_auth()
        account = account_details(self.account_id)
        is_live = _field(account, "is_live")
        if is_live is None:
            is_live = _field(account, "isLive")
        returned_id = _field(account, "account_id")
        if returned_id is None:
            returned_id = _field(account, "ctidTraderAccountId")
        if returned_id is None or int(returned_id) != self.account_id:
            raise PermissionError("cTrader retornou uma conta diferente da solicitada")
        if is_live is not False:
            raise PermissionError("este adaptador aceita somente conta cTrader DEMO confirmada")
        account_auth(self.account_id)
        self._authenticated = True
        return {
            "provider_id": "ctrader_open_api",
            "account_reference": str(self.account_id),
            "capabilities": ["candles:read", "account-mode:demo"],
            "verified": True,
        }

    def _resolve_symbol(self, symbol: str):
        if symbol not in self._symbols:
            resolver = getattr(self.transport, "resolve_symbol", None)
            if not callable(resolver):
                raise RuntimeError("transport cTrader não oferece resolução de símbolos")
            resolved = resolver(self.account_id, symbol)
            if resolved is None:
                raise ValueError(f"símbolo {symbol} não encontrado na conta cTrader")
            symbol_id = _field(resolved, "symbol_id")
            if symbol_id is None:
                symbol_id = _field(resolved, "symbolId")
            digits = _field(resolved, "digits")
            if isinstance(symbol_id, bool) or not isinstance(symbol_id, int) or symbol_id <= 0:
                raise ValueError("symbolId retornado pelo cTrader é inválido")
            if isinstance(digits, bool) or not isinstance(digits, int) or not 0 <= digits <= 12:
                raise ValueError("precisão do símbolo cTrader é inválida")
            self._symbols[symbol] = (symbol_id, digits)
        return self._symbols[symbol]

    def fetch(self, request: MarketDataRequest) -> tuple[Candle, ...]:
        if not self._authenticated:
            raise RuntimeError("cTrader DEMO ainda não concluiu o handshake")
        if not isinstance(request, MarketDataRequest):
            raise TypeError("request deve ser MarketDataRequest")
        try:
            period = _CTRADER_PERIODS[request.timeframe.strip().lower()]
        except KeyError as exc:
            raise ValueError(
                f"timeframe {request.timeframe} não suportado pelo cTrader Open API adapter"
            ) from exc
        symbol_id, digits = self._resolve_symbol(request.symbol.strip())
        fetch = getattr(self.transport, "get_trendbars", None)
        if not callable(fetch):
            raise RuntimeError("transport cTrader não oferece histórico de trendbars")
        # Spotware documents a maximum of five historical requests per second
        # per connection. Serialize and space calls to stay within that limit.
        with self._request_lock:
            wait = 0.2 - (time.monotonic() - self._last_historical_request)
            if wait > 0:
                time.sleep(wait)
            bars = fetch(self.account_id, symbol_id, period, min(request.limit, 1000))
            self._last_historical_request = time.monotonic()
        if not bars:
            raise ValueError("cTrader não retornou trendbars para este símbolo/período")
        candles = []
        for bar in bars:
            low_raw = _field(bar, "low")
            delta_open = _field(bar, "delta_open")
            if delta_open is None:
                delta_open = _field(bar, "deltaOpen")
            delta_high = _field(bar, "delta_high")
            if delta_high is None:
                delta_high = _field(bar, "deltaHigh")
            delta_close = _field(bar, "delta_close")
            if delta_close is None:
                delta_close = _field(bar, "deltaClose")
            minute_stamp = _field(bar, "utc_timestamp_in_minutes")
            if minute_stamp is None:
                minute_stamp = _field(bar, "utcTimestampInMinutes")
            volume = _field(bar, "volume")
            try:
                low = int(low_raw) / 100000.0
                timestamp = datetime.fromtimestamp(int(minute_stamp) * 60, tz=timezone.utc)
                candle = Candle(
                    timestamp=timestamp,
                    open=round((int(low_raw) + int(delta_open)) / 100000.0, digits),
                    high=round((int(low_raw) + int(delta_high)) / 100000.0, digits),
                    low=round(low, digits),
                    close=round((int(low_raw) + int(delta_close)) / 100000.0, digits),
                    volume=float(volume),
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("trendbar cTrader inválida ou incompleta") from exc
            if not candle.is_valid():
                raise ValueError("cTrader retornou candle inválido")
            candles.append(candle)
        candles.sort(key=lambda item: item.timestamp)
        if len({item.timestamp for item in candles}) != len(candles):
            raise ValueError("cTrader retornou timestamps de candles duplicados")
        return tuple(candles[-request.limit:])

    def status(self) -> dict[str, Any]:
        status = getattr(self.transport, "status", None)
        reported = status() if callable(status) else {}
        if not isinstance(reported, dict):
            reported = {}
        return {
            "connected": self._connected and self._authenticated and reported.get("connected", True) is True,
            "account_mode": "DEMO" if self._authenticated else None,
            "last_seen": reported.get("last_seen"),
            "source_id": f"ctrader:{self.account_id}",
            "stored_candles": reported.get("stored_candles", 0),
            "read_only": True,
            "execution_authorized": False,
        }

    def disconnect(self) -> None:
        disconnect = getattr(self.transport, "disconnect", None)
        if callable(disconnect):
            disconnect()
        self._connected = False
        self._authenticated = False
