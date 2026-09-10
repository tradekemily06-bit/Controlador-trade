from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from execution.p128_ctrader_demo_auth import (
    CTraderTokenSnapshot,
    CTraderTokenProvider,
)

CTRADER_DEMO_HOST = "demo.ctraderapi.com"
CTRADER_DEMO_PORT = 5035


class CTraderClient(Protocol):
    def connect(self) -> Any: ...
    def send(self, request: Any) -> Any: ...
    def disconnect(self) -> Any: ...


class CTraderClientFactory(Protocol):
    def __call__(self, client_id: str, client_secret: str) -> CTraderClient: ...


@dataclass(frozen=True)
class CTraderCredentials:
    client_id: str
    client_secret: str

    @classmethod
    def from_environment(cls) -> "CTraderCredentials":
        client_id = os.getenv("CTRADER_CLIENT_ID", "").strip()
        client_secret = os.getenv("CTRADER_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValueError("CTRADER_CLIENT_ID/CTRADER_CLIENT_SECRET obrigatórios")
        return cls(client_id, client_secret)


@dataclass(frozen=True)
class CTraderAccessToken:
    access_token: str
    refresh_token: str | None
    expires_at: float

    def snapshot(self) -> CTraderTokenSnapshot:
        return CTraderTokenSnapshot(
            expires_in=max(0, int(self.expires_at - time.time())),
            has_access_token=bool(self.access_token),
            has_refresh_token=bool(self.refresh_token),
        )


class InMemoryTokenProvider(CTraderTokenProvider):
    """Runtime-only token provider. Nothing here is persisted to the repository."""

    def __init__(self) -> None:
        self._token: CTraderAccessToken | None = None

    def set_token(self, access_token: str, expires_in: int, refresh_token: str | None = None) -> None:
        if not access_token.strip():
            raise ValueError("access_token obrigatório")
        if expires_in <= 0:
            raise ValueError("expires_in inválido")
        self._token = CTraderAccessToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
        )

    def snapshot(self) -> CTraderTokenSnapshot:
        if self._token is None:
            return CTraderTokenSnapshot(0, False, False)
        return self._token.snapshot()

    @property
    def access_token(self) -> str:
        if self._token is None or self._token.snapshot().expires_in <= 0:
            raise RuntimeError("sessão cTrader DEMO sem token válido")
        return self._token.access_token


class CTraderDemoConnection:
    """Real cTrader DEMO connection boundary using the official Python SDK.

    Network I/O is intentionally kept outside the decision core. REAL is never
    selected by this class.
    """

    endpoint = (CTRADER_DEMO_HOST, CTRADER_DEMO_PORT)

    def __init__(self, credentials: CTraderCredentials, token_provider: InMemoryTokenProvider,
                 client_factory: CTraderClientFactory) -> None:
        self._credentials = credentials
        self._tokens = token_provider
        self._client_factory = client_factory
        self._client: CTraderClient | None = None
        self._account_id: int | None = None

    @property
    def account_id(self) -> int | None:
        return self._account_id

    def connect(self) -> CTraderClient:
        if self._tokens.snapshot().expires_in <= 0:
            raise RuntimeError("autorize o Controlador Trading no cTrader antes de conectar")
        self._client = self._client_factory(
            self._credentials.client_id,
            self._credentials.client_secret,
        )
        self._client.connect()
        return self._client

    def application_auth_request(self) -> Any:
        """Build the SDK application-auth message without exposing credentials in logs."""
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq
        except ImportError as exc:
            raise RuntimeError("instale ctrader-open-api antes de usar a conexão") from exc
        request = ProtoOAApplicationAuthReq()
        request.clientId = self._credentials.client_id
        request.clientSecret = self._credentials.client_secret
        return request

    def account_list_request(self) -> Any:
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAGetAccountListByAccessTokenReq
        except ImportError as exc:
            raise RuntimeError("instale ctrader-open-api antes de usar a conexão") from exc
        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = self._tokens.access_token
        return request

    def account_auth_request(self, account_id: int) -> Any:
        if account_id <= 0:
            raise ValueError("account_id inválido")
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAccountAuthReq
        except ImportError as exc:
            raise RuntimeError("instale ctrader-open-api antes de usar a conexão") from exc
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = account_id
        request.accessToken = self._tokens.access_token
        self._account_id = account_id
        return request

    def new_client_message_id(self) -> str:
        return uuid.uuid4().hex

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.disconnect()
            self._client = None
