from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from execution.ctrader_demo_connection import (
    CTraderCredentials,
    InMemoryTokenProvider,
    CTraderDemoConnection,
)

CTRADER_TOKEN_URL = "https://openapi.ctrader.com/apps/token"


def exchange_authorization_code(
    credentials: CTraderCredentials,
    authorization_code: str,
    redirect_uri: str,
) -> InMemoryTokenProvider:
    """Exchange the short-lived OAuth code for a runtime-only token."""
    if not authorization_code.strip():
        raise ValueError("authorization_code obrigatório")
    if not redirect_uri.strip():
        raise ValueError("redirect_uri obrigatório")

    query = urlencode({
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": redirect_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
    })
    request = Request(
        f"{CTRADER_TOKEN_URL}?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # cTrader documents client_secret as a query parameter for this GET.
        # Never propagate the HTTP error object because its string form may
        # contain the complete URL, including the secret.
        raise RuntimeError(f"cTrader OAuth HTTP error ({exc.code})") from None
    except URLError:
        # Avoid exposing the request URL through a transport exception.
        raise RuntimeError("cTrader OAuth transport error") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("cTrader OAuth returned invalid JSON") from None

    if payload.get("errorCode"):
        raise RuntimeError(
            f"cTrader OAuth recusado: {payload.get('description') or payload['errorCode']}"
        )

    provider = InMemoryTokenProvider()
    provider.set_token(
        payload["accessToken"],
        int(payload["expiresIn"]),
        payload.get("refreshToken"),
    )
    return provider


def create_demo_connection(
    credentials: CTraderCredentials,
    token_provider: InMemoryTokenProvider,
) -> CTraderDemoConnection:
    """Create the official Spotware SDK DEMO connection."""
    try:
        from ctrader_open_api import Client, EndPoints, TcpProtocol
    except ImportError as exc:
        raise RuntimeError("instale ctrader-open-api antes de conectar") from exc

    def factory(_client_id: str, _client_secret: str):
        return Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)

    return CTraderDemoConnection(credentials, token_provider, factory)


def token_is_usable(provider: InMemoryTokenProvider) -> bool:
    return provider.snapshot().has_access_token and provider.snapshot().expires_in > 0
