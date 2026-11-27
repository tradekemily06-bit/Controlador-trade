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


def _strict_integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("cTrader integer field required")
    return value


def _finite_float(value: Any) -> float:
    import math

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("cTrader numeric field required")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError("cTrader finite numeric field required") from exc
    if not math.isfinite(number):
        raise ValueError("cTrader finite numeric field required")
    return number


class CTraderReadOnlyMarketDataAdapter:
    """Broker-neutral adapter over a host-owned cTrader Open API transport.

    Transport contract:
      connect(), application_auth(), account_details(account_id),
      account_auth(account_id), resolve_symbol(account_id, symbol),
      get_trendbars(account_id, symbol_id, period, count), status(), disconnect().
    """

    def __init__(
        self, transport: Any, *, account_id: int, source: str = "ctrader_open_api",
        access_token_resolver=None,
    ) -> None:
        if transport is None:
            raise ValueError("cTrader transport é obrigatório")
        if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id cTrader inválido")
        self.transport = transport
        self.account_id = account_id
        self.source = source
        if access_token_resolver is not None and not callable(access_token_resolver):
            raise ValueError("access_token_resolver deve ser executável")
        self.access_token_resolver = access_token_resolver
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
        try:
            verified_account_id = _strict_integer(returned_id)
        except ValueError as exc:
            raise PermissionError("cTrader retornou um identificador de conta inválido") from exc
        if verified_account_id != self.account_id:
            raise PermissionError("cTrader retornou uma conta diferente da solicitada")
        if is_live is not False:
            raise PermissionError("este adaptador aceita somente conta cTrader DEMO confirmada")
        account_auth(self.account_id)
        self._authenticated = True
        capabilities = ["candles:read", "account-mode:demo"]
        if callable(getattr(self.transport, "subscribe_spots", None)):
            capabilities.append("quotes:stream")
        if callable(getattr(self.transport, "subscribe_live_trendbars", None)):
            capabilities.append("candles:stream")
        return {
            "provider_id": "ctrader_open_api",
            "account_reference": str(self.account_id),
            "capabilities": capabilities,
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

    def subscribe_live_quotes(self, symbol: str, callback) -> None:
        """Subscribe to provider-pushed bid/ask updates without polling the API."""
        if not self._authenticated:
            raise RuntimeError("cTrader DEMO ainda não concluiu o handshake")
        if not callable(callback):
            raise ValueError("callback de cotação deve ser executável")
        symbol_id, digits = self._resolve_symbol(symbol.strip())
        subscribe = getattr(self.transport, "subscribe_spots", None)
        if not callable(subscribe):
            raise RuntimeError("transport cTrader não oferece streaming spot")
        def normalized(event):
            returned_symbol = _field(event, "symbol_id")
            if returned_symbol != symbol_id:
                return
            bid_raw = _field(event, "bid")
            ask_raw = _field(event, "ask")
            timestamp_raw = _field(event, "timestamp")
            try:
                bid = round(_strict_integer(bid_raw) / 100000.0, digits) if bid_raw is not None else None
                ask = round(_strict_integer(ask_raw) / 100000.0, digits) if ask_raw is not None else None
                if bid is None and ask is None:
                    return
                if bid is not None and ask is not None and bid > ask:
                    return
                if (bid is not None and bid <= 0) or (ask is not None and ask <= 0):
                    return
                timestamp = None
                if timestamp_raw is not None:
                    stamp = _finite_float(timestamp_raw)
                    if stamp <= 0:
                        return
                    if stamp > 10_000_000_000:
                        stamp /= 1000.0
                    timestamp = datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError, OSError):
                return
            callback({
                "provider_id": "ctrader_open_api",
                "account_id": self.account_id,
                "symbol": symbol.strip(),
                "bid": bid,
                "ask": ask,
                "timestamp": timestamp,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "read_only": True,
                "execution_authorized": False,
            })
        subscribe(self.account_id, symbol_id, normalized)

    def unsubscribe_live_quotes(self, symbol: str) -> None:
        if not self._authenticated:
            raise RuntimeError("cTrader DEMO ainda não concluiu o handshake")
        symbol_id, _digits = self._resolve_symbol(symbol.strip())
        unsubscribe = getattr(self.transport, "unsubscribe_spots", None)
        if not callable(unsubscribe):
            raise RuntimeError("transport cTrader não oferece cancelamento de streaming spot")
        unsubscribe(self.account_id, symbol_id)

    def subscribe_live_candles(self, symbol: str, timeframe: str, callback) -> None:
        """Subscribe to Spotware live trendbars, which carry the latest closed bar."""
        if not self._authenticated:
            raise RuntimeError("cTrader DEMO ainda não concluiu o handshake")
        if not callable(callback):
            raise ValueError("callback de candle deve ser executável")
        clean_symbol = symbol.strip()
        clean_timeframe = timeframe.strip().lower()
        try:
            period = _CTRADER_PERIODS[clean_timeframe]
        except KeyError as exc:
            raise ValueError(f"timeframe {timeframe} não suportado pelo cTrader") from exc
        symbol_id, digits = self._resolve_symbol(clean_symbol)
        subscribe = getattr(self.transport, "subscribe_live_trendbars", None)
        if not callable(subscribe):
            raise RuntimeError("transport cTrader não oferece streaming de candles")
        def normalized(event):
            if _field(event, "symbol_id") != symbol_id:
                return
            if str(_field(event, "period") or "").upper() != period:
                return
            bar = _field(event, "trendbar")
            if bar is None:
                return
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
                candle = Candle(
                    timestamp=datetime.fromtimestamp(
                        _strict_integer(minute_stamp) * 60, tz=timezone.utc
                    ),
                    open=round((_strict_integer(low_raw) + _strict_integer(delta_open)) / 100000.0, digits),
                    high=round((_strict_integer(low_raw) + _strict_integer(delta_high)) / 100000.0, digits),
                    low=round(_strict_integer(low_raw) / 100000.0, digits),
                    close=round((_strict_integer(low_raw) + _strict_integer(delta_close)) / 100000.0, digits),
                    volume=_finite_float(volume),
                )
            except (TypeError, ValueError, OverflowError, OSError):
                return
            if not candle.is_valid():
                return
            callback({
                "provider_id": "ctrader_open_api",
                "account_id": self.account_id,
                "symbol": clean_symbol,
                "timeframe": clean_timeframe,
                "candle": candle,
                "closed": True,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "read_only": True,
                "execution_authorized": False,
            })
        subscribe(self.account_id, symbol_id, period, normalized)

    def unsubscribe_live_candles(self, symbol: str, timeframe: str) -> None:
        if not self._authenticated:
            raise RuntimeError("cTrader DEMO ainda não concluiu o handshake")
        clean_timeframe = timeframe.strip().lower()
        try:
            period = _CTRADER_PERIODS[clean_timeframe]
        except KeyError as exc:
            raise ValueError(f"timeframe {timeframe} não suportado pelo cTrader") from exc
        symbol_id, _digits = self._resolve_symbol(symbol.strip())
        unsubscribe = getattr(self.transport, "unsubscribe_live_trendbars", None)
        if not callable(unsubscribe):
            raise RuntimeError("transport cTrader não oferece cancelamento de candles")
        unsubscribe(self.account_id, symbol_id, period)

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
                low_value = _strict_integer(low_raw)
                timestamp = datetime.fromtimestamp(
                    _strict_integer(minute_stamp) * 60, tz=timezone.utc
                )
                candle = Candle(
                    timestamp=timestamp,
                    open=round((low_value + _strict_integer(delta_open)) / 100000.0, digits),
                    high=round((low_value + _strict_integer(delta_high)) / 100000.0, digits),
                    low=round(low_value / 100000.0, digits),
                    close=round((low_value + _strict_integer(delta_close)) / 100000.0, digits),
                    volume=_finite_float(volume),
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
            "account_mode": "DEMO" if self._connected and self._authenticated and reported.get("connected", True) is True else None,
            "last_seen": reported.get("last_seen"),
            "active_spot_symbols": reported.get("active_spot_symbols", 0),
            "active_trendbar_streams": reported.get("active_trendbar_streams", 0),
            "spot_event_queue_depth": reported.get("spot_event_queue_depth", 0),
            "spot_event_overflow_count": reported.get("spot_event_overflow_count", 0),
            "source_id": f"ctrader:{self.account_id}",
            "stored_candles": reported.get("stored_candles", 0),
            "read_only": True,
            "execution_authorized": False,
        }

    def reconnect(self) -> dict[str, Any]:
        reconnect = getattr(self.transport, "reconnect", None)
        if not callable(reconnect):
            raise RuntimeError("transport cTrader não oferece reconexão segura")
        try:
            # OAuth refresh worker may have rotated the encrypted token since
            # this adapter was created. Resolve it again for the same trusted
            # tenant/account before reconnecting; never reuse an expired token
            # merely because the old transport object is still in memory.
            if self.access_token_resolver is not None:
                access_token = self.access_token_resolver()
                update_token = getattr(self.transport, "update_access_token", None)
                if not isinstance(access_token, str) or not access_token.strip():
                    raise PermissionError("token OAuth cTrader renovado indisponível")
                if not callable(update_token):
                    raise RuntimeError("transport cTrader não aceita rotação segura de token")
                update_token(access_token)
            details = reconnect()
        except Exception:
            self._connected = False
            self._authenticated = False
            raise
        if not isinstance(details, dict) or details.get("is_live") is not False:
            self._connected = False
            self._authenticated = False
            raise PermissionError("reconexão cTrader não confirmou conta DEMO")
        self._connected = True
        self._authenticated = True
        return {
            "connected": True,
            "account_id": self.account_id,
            "account_mode": "DEMO",
            "read_only": True,
            "execution_authorized": False,
        }

    def disconnect(self) -> None:
        disconnect = getattr(self.transport, "disconnect", None)
        if callable(disconnect):
            disconnect()
        self._connected = False
        self._authenticated = False
