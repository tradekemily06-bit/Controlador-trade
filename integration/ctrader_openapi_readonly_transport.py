"""Official Spotware OpenApiPy transport for read-only cTrader DEMO sessions.

The SDK is imported lazily so installations without cTrader support can still
start. This transport owns no reactor shutdown: Twisted reactors cannot be
restarted safely. A single process-wide reactor services all account clients.
Only the DEMO endpoint and read-only Open API messages are exposed.
"""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
from datetime import datetime, timezone
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
        self._last_seen: str | None = None
        self._account_id: int | None = None
        self._account_authenticated = False
        self._symbols_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _field(obj: Any, *names: str):
        for name in names:
            if isinstance(obj, dict) and name in obj:
                return obj[name]
            value = getattr(obj, name, None)
            if value is not None:
                return value
        return None

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

            self._client.setConnectedCallback(connected)
            self._client.setDisconnectedCallback(disconnected)
            self._client.setMessageReceivedCallback(received)
            _SharedTwistedReactor.call(self._client.startService, self._timeout)
        if not self._connected.wait(self._timeout):
            self.disconnect()
            raise TimeoutError("conexão TCP DEMO do cTrader não foi estabelecida")

    def _send(self, request):
        if not self._connected.is_set() or self._client is None:
            raise RuntimeError("transporte cTrader não conectado")
        return _SharedTwistedReactor.call(
            lambda: self._client.send(request), self._timeout
        )

    def application_auth(self) -> None:
        request = self._messages["application_auth"]()
        request.clientId = self._client_id
        request.clientSecret = self._client_secret
        self._send(request)

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
                if not isinstance(is_live, bool):
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
        }

    def disconnect(self) -> None:
        client = self._client
        self._connected.clear()
        self._account_authenticated = False
        self._account_id = None
        self._symbols_cache.clear()
        if client is not None:
            try:
                _SharedTwistedReactor.call(client.stopService, self._timeout)
            except Exception:
                pass
        self._client = None
