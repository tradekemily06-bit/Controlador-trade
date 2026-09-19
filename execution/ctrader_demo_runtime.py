from __future__ import annotations

import json
import time
import os
import hmac
from urllib.parse import urlencode
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
    configured_redirect_uri = os.environ.get("CTRADER_REDIRECT_URI", "").strip()
    if configured_redirect_uri and not hmac.compare_digest(redirect_uri.strip(), configured_redirect_uri):
        raise ValueError("redirect_uri não corresponde ao URI configurado")

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
    except Exception as exc:
        raise RuntimeError(f"falha na comunicação OAuth cTrader: {type(exc).__name__}") from exc

    if payload.get("errorCode"):
        raise RuntimeError(
            "cTrader OAuth recusado pelo provedor."
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
