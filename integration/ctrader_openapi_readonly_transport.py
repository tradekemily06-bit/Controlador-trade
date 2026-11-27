"""Official Spotware OpenApiPy transport for read-only cTrader DEMO sessions.

The SDK is imported lazily so installations without cTrader support can still
start. This transport owns no reactor shutdown: Twisted reactors cannot be
restarted safely. A single process-wide reactor services all account clients.
Only the DEMO endpoint and read-only Open API messages are exposed.
"""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
from datetime import datetime, timezone
import queue
import threading
import time
from typing import Any


class _SharedTwistedReactor:
    _guard = threading.Lock()
    _reactor = None
    _thread = None
    _started = threading.Event()

    @classmethod
    def get(cls):
        with cls._guard:
            if cls._reactor is not None:
                return cls._reactor
            try:
                from twisted.internet import reactor
            except ImportError as exc:
                raise RuntimeError(
                    "cTrader Open API requer o pacote opcional ctrader-open-api"
                ) from exc
            cls._reactor = reactor
            if not reactor.running:
                def run():
                    cls._started.set()
                    reactor.run(installSignalHandlers=False)

                cls._thread = threading.Thread(
                    target=run, name="ctrader-openapi-reactor", daemon=True
                )
                cls._thread.start()
                if not cls._started.wait(5):
                    raise RuntimeError("não foi possível iniciar o reactor cTrader")
            return reactor

    @classmethod
    def call(cls, callback, timeout: float):
        reactor = cls.get()
        future: Future = Future()

        def invoke():
            if future.cancelled():
                return
            try:
                result = callback()
            except Exception as exc:
                future.set_exception(exc)
                return
            if hasattr(result, "addCallbacks"):
                def success(value):
                    if not future.done():
                        future.set_result(value)
                    return value

                def failure(reason):
                    if not future.done():
                        future.set_exception(RuntimeError("falha na comunicação cTrader"))
                    return None

                result.addCallbacks(success, failure)
            else:
                future.set_result(result)

        reactor.callFromThread(invoke)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError("tempo limite aguardando resposta do cTrader") from exc


class CTraderOpenApiReadOnlyTransport:
    """Synchronous boundary over Spotware's asynchronous official Python SDK.

    Instantiate one transport per provider account. Access tokens and app
    credentials are accepted only from trusted server-side secret resolution.
    No order, position mutation, or money-transfer message is implemented.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        access_token: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        for name, value in (
            ("client_id", client_id),
            ("client_secret", client_secret),
            ("access_token", access_token),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cTrader é obrigatório")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 2 <= timeout_seconds <= 60:
            raise ValueError("timeout_seconds deve ficar entre 2 e 60")
        try:
            from ctrader_open_api import Client, TcpProtocol, EndPoints
            from ctrader_open_api.messages.OpenApiMessages_pb2 import (
                ProtoOAApplicationAuthReq,
                ProtoOAGetAccountListByAccessTokenReq,
                ProtoOAAccountAuthReq,
                ProtoOASymbolsListReq,
                ProtoOAGetTrendbarsReq,
                ProtoOASubscribeSpotsReq,
                ProtoOAUnsubscribeSpotsReq,
                ProtoOASubscribeLiveTrendbarReq,
                ProtoOAUnsubscribeLiveTrendbarReq,
            )
            from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATrendbarPeriod
        except ImportError as exc:
            raise RuntimeError(
                "SDK oficial ausente. Instale ctrader-open-api no ambiente do aplicativo."
            ) from exc

        self._Client = Client
        self._TcpProtocol = TcpProtocol
        self._host = EndPoints.PROTOBUF_DEMO_HOST
        self._port = EndPoints.PROTOBUF_PORT
        self._messages = {
            "application_auth": ProtoOAApplicationAuthReq,
            "account_list": ProtoOAGetAccountListByAccessTokenReq,
            "account_auth": ProtoOAAccountAuthReq,
            "symbols": ProtoOASymbolsListReq,
            "trendbars": ProtoOAGetTrendbarsReq,
            "subscribe_spots": ProtoOASubscribeSpotsReq,
            "unsubscribe_spots": ProtoOAUnsubscribeSpotsReq,
            "subscribe_trendbars": ProtoOASubscribeLiveTrendbarReq,
            "unsubscribe_trendbars": ProtoOAUnsubscribeLiveTrendbarReq,
        }
        self._period_enum = ProtoOATrendbarPeriod
        self._client_id = client_id.strip()
        self._client_secret = client_secret
        self._access_token = access_token.strip()
        self._timeout = float(timeout_seconds)
        self._client = None
        self._connected = threading.Event()
        self._disconnected = threading.Event()
        self._lock = threading.RLock()
        self._reconnect_lock = threading.Lock()
        self._last_seen: str | None = None
        self._account_id: int | None = None
        self._account_authenticated = False
        self._symbols_cache: dict[str, dict[str, Any]] = {}
        self._spot_callbacks: dict[int, Any] = {}
        self._trendbar_callbacks: dict[tuple[int, str], Any] = {}
        # Spot subscriptions created only to carry trendbar events are tracked
        # separately from explicit quote subscriptions for safe cleanup.
        self._trendbar_spot_only: set[int] = set()
        self._spot_queue: queue.Queue = queue.Queue(maxsize=2048)
        self._spot_worker: threading.Thread | None = None
        self._spot_worker_stop = threading.Event()
        self._spot_overflow_count = 0
        self._last_spot_overflow_at: str | None = None

    @staticmethod
    def _field(obj: Any, *names: str):
        for name in names:
            if isinstance(obj, dict) and name in obj:
                return obj[name]
            value = getattr(obj, name, None)
            if value is not None:
                return value
        return None

    @staticmethod
    def _field_present(obj: Any, name: str) -> bool:
        if isinstance(obj, dict):
            return name in obj and obj[name] is not None
        has_field = getattr(obj, "HasField", None)
        if callable(has_field):
            try:
                return bool(has_field(name))
            except (ValueError, TypeError):
                pass
        list_fields = getattr(obj, "ListFields", None)
        if callable(list_fields):
            try:
                return any(getattr(descriptor, "name", None) == name for descriptor, _value in list_fields())
            except Exception:
                pass
        return getattr(obj, name, None) is not None

    def connect(self) -> None:
        with self._lock:
            if self._client is not None and self._connected.is_set():
                return
            self._connected.clear()
            self._disconnected.clear()
            self._client = self._Client(self._host, self._port, self._TcpProtocol)

            def connected(_client):
                self._connected.set()
                self._last_seen = datetime.now(timezone.utc).isoformat()

            def disconnected(_client, _reason):
                self._connected.clear()
                self._account_authenticated = False
                self._disconnected.set()

            def received(_client, _message):
                self._last_seen = datetime.now(timezone.utc).isoformat()
                symbol_id = self._field(_message, "symbolId")
                if symbol_id is None:
                    return
                try:
                    symbol_key = int(symbol_id)
                except (TypeError, ValueError, OverflowError):
                    return
                with self._lock:
                    callback = self._spot_callbacks.get(symbol_key)
                event_account_id = self._field(_message, "ctidTraderAccountId")
                try:
                    if int(event_account_id) != self._account_id:
                        return
                except (TypeError, ValueError, OverflowError):
                    return
                event = {
                    "account_id": int(event_account_id),
                    "symbol_id": symbol_key,
                    "bid": self._field(_message, "bid"),
                    "ask": self._field(_message, "ask"),
                    "timestamp": self._field(_message, "timestamp"),
                }
                callbacks = []
                if callback is not None:
                    callbacks.append((callback, event))
                trendbars = self._field(_message, "trendbar") or ()
                with self._lock:
                    trendbar_targets = [
                        (period, target)
                        for (registered_symbol, period), target in self._trendbar_callbacks.items()
                        if registered_symbol == symbol_key
                    ]
                for period, target in trendbar_targets:
                    for bar in trendbars:
                        callbacks.append((target, {
                            **event,
                            "period": period,
                            "trendbar": bar,
                        }))
                for target, payload in callbacks:
                    try:
                        self._spot_queue.put_nowait((target, payload))
                    except queue.Full:
                        with self._lock:
                            self._spot_overflow_count += 1
                        self._last_spot_overflow_at = datetime.now(timezone.utc).isoformat()

            self._client.setConnectedCallback(connected)
            self._client.setDisconnectedCallback(disconnected)
            self._client.setMessageReceivedCallback(received)
            _SharedTwistedReactor.call(self._client.startService, self._timeout)
        if not self._connected.wait(self._timeout):
            self.disconnect()
            raise TimeoutError("conexão TCP DEMO do cTrader não foi estabelecida")

    def reconnect(self) -> dict[str, Any]:
        """Re-authenticate the selected DEMO account and restore read-only streams."""
        with self._reconnect_lock:
            account_id = self._account_id
            if account_id is None:
                raise RuntimeError("conta cTrader não foi selecionada para reconexão")
            if self._connected.is_set() and self._account_authenticated:
                return {"account_id": account_id, "is_live": False}
            spot_callbacks = dict(self._spot_callbacks)
            trendbar_callbacks = dict(self._trendbar_callbacks)
            spot_only = set(self._trendbar_spot_only)
            previous_client = self._client
            self._connected.clear()
            self._account_authenticated = False
            if previous_client is not None:
                try:
                    _SharedTwistedReactor.call(previous_client.stopService, self._timeout)
                except Exception:
                    pass
            self._client = None
            try:
                self.connect()
                self.application_auth()
                details = self.account_details(account_id)
                if details.get("is_live") is not False:
                    raise PermissionError("reconexão recusada: a conta cTrader não é DEMO")
                self.account_auth(account_id)
                self._start_spot_worker()
                # Spot subscription must be restored before trendbar subscriptions.
                for symbol_id in sorted(spot_callbacks):
                    request = self._messages["subscribe_spots"]()
                    request.ctidTraderAccountId = account_id
                    request.symbolId.append(symbol_id)
                    request.subscribeToSpotTimestamp = True
                    self._send(request)
                for symbol_id, period in sorted(trendbar_callbacks):
                    request = self._messages["subscribe_trendbars"]()
                    request.ctidTraderAccountId = account_id
                    request.symbolId = symbol_id
                    request.period = self._period_enum.Value(period)
                    self._send(request)
                return details
            except Exception:
                # Keep the desired subscriptions and account identity so a later
                # bounded retry can restore them; never report the session healthy.
                self._account_id = account_id
                self._account_authenticated = False
                self._spot_callbacks = spot_callbacks
                self._trendbar_callbacks = trendbar_callbacks
                self._trendbar_spot_only = spot_only
                self._connected.clear()
                raise

    def _send(self, request):
        if not self._connected.is_set() or self._client is None:
            raise RuntimeError("transporte cTrader não conectado")
        return _SharedTwistedReactor.call(
            lambda: self._client.send(request), self._timeout
        )

    def _start_spot_worker(self) -> None:
        if self._spot_worker is not None and self._spot_worker.is_alive():
            return
        self._spot_worker_stop.clear()

        def dispatch():
            while not self._spot_worker_stop.is_set() or not self._spot_queue.empty():
                try:
                    callback, event = self._spot_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                try:
                    callback(event)
                except Exception:
                    # Consumer failures must not interrupt the Twisted reactor
                    # or prevent delivery of later market events.
                    pass
                finally:
                    self._spot_queue.task_done()

        self._spot_worker = threading.Thread(
            target=dispatch, name="ctrader-spot-event-dispatch", daemon=True
        )
        self._spot_worker.start()

    def subscribe_spots(self, account_id: int, symbol_id: int, callback) -> None:
        self._require_account(account_id)
        if isinstance(symbol_id, bool) or not isinstance(symbol_id, int) or symbol_id <= 0:
            raise ValueError("symbol_id cTrader inválido")
        if not callable(callback):
            raise ValueError("callback de cotação deve ser executável")
        with self._lock:
            if symbol_id in self._spot_callbacks:
                raise ValueError("já existe uma assinatura spot para este símbolo nesta conta")
            self._spot_callbacks[symbol_id] = callback
        self._start_spot_worker()
        request = self._messages["subscribe_spots"]()
        request.ctidTraderAccountId = account_id
        request.symbolId.append(symbol_id)
        request.subscribeToSpotTimestamp = True
        try:
            self._send(request)
        except Exception:
            with self._lock:
                self._spot_callbacks.pop(symbol_id, None)
            raise

    def unsubscribe_spots(self, account_id: int, symbol_id: int) -> None:
        self._require_account(account_id)
        if isinstance(symbol_id, bool) or not isinstance(symbol_id, int) or symbol_id <= 0:
            raise ValueError("symbol_id cTrader inválido")
        request = self._messages["unsubscribe_spots"]()
        request.ctidTraderAccountId = account_id
        request.symbolId.append(symbol_id)
        self._send(request)
        with self._lock:
            self._spot_callbacks.pop(symbol_id, None)

    def subscribe_live_trendbars(
        self, account_id: int, symbol_id: int, period: str, callback
    ) -> None:
        self._require_account(account_id)
        if isinstance(symbol_id, bool) or not isinstance(symbol_id, int) or symbol_id <= 0:
            raise ValueError("symbol_id cTrader inválido")
        if not isinstance(period, str) or not period.strip():
            raise ValueError("period cTrader inválido")
        if not callable(callback):
            raise ValueError("callback de trendbar deve ser executável")
        key = (symbol_id, period.strip().upper())
        with self._lock:
            if key in self._trendbar_callbacks:
                raise ValueError("já existe assinatura de trendbar para este símbolo/período")
        # Spot events are the required carrier for live trendbars in Spotware Open API.
        if symbol_id not in self._spot_callbacks:
            self.subscribe_spots(account_id, symbol_id, lambda _event: None)
            with self._lock:
                self._trendbar_spot_only.add(symbol_id)
        request = self._messages["subscribe_trendbars"]()
        request.ctidTraderAccountId = account_id
        request.symbolId = symbol_id
        request.period = self._period_enum.Value(key[1])
        with self._lock:
            self._trendbar_callbacks[key] = callback
        try:
            self._send(request)
        except Exception:
            with self._lock:
                self._trendbar_callbacks.pop(key, None)
                cleanup_spot = symbol_id in self._trendbar_spot_only and not any(
                    registered_symbol == symbol_id
                    for registered_symbol, _period in self._trendbar_callbacks
                )
                if cleanup_spot:
                    self._trendbar_spot_only.discard(symbol_id)
            if cleanup_spot:
                self.unsubscribe_spots(account_id, symbol_id)
            raise

    def unsubscribe_live_trendbars(
        self, account_id: int, symbol_id: int, period: str
    ) -> None:
        self._require_account(account_id)
        key = (symbol_id, str(period).strip().upper())
        request = self._messages["unsubscribe_trendbars"]()
        request.ctidTraderAccountId = account_id
        request.symbolId = symbol_id
        request.period = self._period_enum.Value(key[1])
        self._send(request)
        with self._lock:
            self._trendbar_callbacks.pop(key, None)
            no_more_trendbars = not any(
                registered_symbol == symbol_id
                for registered_symbol, _period in self._trendbar_callbacks
            )
            cleanup_spot = no_more_trendbars and symbol_id in self._trendbar_spot_only
            if cleanup_spot:
                self._trendbar_spot_only.discard(symbol_id)
        if cleanup_spot:
            self.unsubscribe_spots(account_id, symbol_id)

    def application_auth(self) -> None:
        request = self._messages["application_auth"]()
        request.clientId = self._client_id
        request.clientSecret = self._client_secret
        self._send(request)

    def list_accounts(self) -> tuple[dict[str, Any], ...]:
        """Return only safe account identifiers and DEMO/REAL flags from OAuth."""
        request = self._messages["account_list"]()
        request.accessToken = self._access_token
        response = self._send(request)
        accounts = self._field(response, "ctidTraderAccount") or ()
        output = []
        for account in accounts:
            raw_id = self._field(account, "ctidTraderAccountId")
            is_live = self._field(account, "isLive")
            if raw_id is None or not self._field_present(account, "isLive") or not isinstance(is_live, bool):
                raise PermissionError("Spotware retornou uma conta sem confirmação de ID/modo")
            try:
                account_id = int(raw_id)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Spotware retornou um identificador de conta inválido") from exc
            if account_id <= 0:
                raise ValueError("Spotware retornou um identificador de conta inválido")
            output.append({"account_id": account_id, "is_live": is_live})
        return tuple(output)

    def account_details(self, account_id: int) -> dict[str, Any]:
        if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id cTrader inválido")
        request = self._messages["account_list"]()
        request.accessToken = self._access_token
        response = self._send(request)
        accounts = self._field(response, "ctidTraderAccount") or ()
        for account in accounts:
            returned_id = self._field(account, "ctidTraderAccountId")
            if returned_id is not None and int(returned_id) == account_id:
                is_live = self._field(account, "isLive")
                if not self._field_present(account, "isLive") or not isinstance(is_live, bool):
                    raise PermissionError("Spotware não confirmou o tipo DEMO/REAL da conta")
                self._account_id = account_id
                return {"account_id": account_id, "is_live": is_live}
        raise PermissionError("conta não autorizada pelo token OAuth cTrader")

    def account_auth(self, account_id: int) -> None:
        if self._account_id != account_id:
            raise PermissionError("conta cTrader não passou pela verificação OAuth")
        request = self._messages["account_auth"]()
        request.ctidTraderAccountId = account_id
        request.accessToken = self._access_token
        self._send(request)
        self._account_authenticated = True

    def resolve_symbol(self, account_id: int, symbol: str) -> dict[str, Any]:
        self._require_account(account_id)
        clean = str(symbol).strip()
        if clean in self._symbols_cache:
            return self._symbols_cache[clean]
        request = self._messages["symbols"]()
        request.ctidTraderAccountId = account_id
        response = self._send(request)
        for item in self._field(response, "symbol") or ():
            name = self._field(item, "symbolName")
            if isinstance(name, str) and name.casefold() == clean.casefold():
                result = {
                    "symbol_id": int(self._field(item, "symbolId")),
                    "digits": int(self._field(item, "digits")),
                }
                self._symbols_cache[clean] = result
                return result
        raise ValueError("símbolo não disponível na conta cTrader")

    def get_trendbars(self, account_id: int, symbol_id: int, period: str, count: int):
        self._require_account(account_id)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1000:
            raise ValueError("count deve ficar entre 1 e 1000")
        request = self._messages["trendbars"]()
        request.ctidTraderAccountId = account_id
        request.symbolId = symbol_id
        request.period = self._period_enum.Value(period)
        request.toTimestamp = int(time.time() * 1000)
        request.fromTimestamp = 0
        request.count = count
        response = self._send(request)
        return tuple(self._field(response, "trendbar") or ())

    def _require_account(self, account_id: int) -> None:
        if not self._account_authenticated or self._account_id != account_id:
            raise PermissionError("conta cTrader não autenticada nesta sessão")

    def status(self) -> dict[str, Any]:
        return {
            "connected": self._connected.is_set() and not self._disconnected.is_set(),
            "account_authenticated": self._account_authenticated,
            "account_mode": "DEMO" if self._account_authenticated else None,
            "last_seen": self._last_seen,
            "active_spot_symbols": len(self._spot_callbacks),
            "active_trendbar_streams": len(self._trendbar_callbacks),
            "spot_event_queue_depth": self._spot_queue.qsize(),
            "spot_event_overflow_count": self._spot_overflow_count,
            "last_spot_overflow_at": self._last_spot_overflow_at,
        }

    def disconnect(self) -> None:
        client = self._client
        self._connected.clear()
        self._account_authenticated = False
        self._account_id = None
        self._symbols_cache.clear()
        with self._lock:
            self._spot_callbacks.clear()
            self._trendbar_callbacks.clear()
            self._trendbar_spot_only.clear()
        self._spot_worker_stop.set()
        worker = self._spot_worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)
        self._spot_worker = None
        if client is not None:
            try:
                _SharedTwistedReactor.call(client.stopService, self._timeout)
            except Exception:
                pass
        self._client = None
