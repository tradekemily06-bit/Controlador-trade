from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from execution.ctrader_demo_connection import (
    CTraderCredentials,
    InMemoryTokenProvider,
    CTraderDemoConnection,
)
from execution.p128_ctrader_demo_auth import _validate_ctrader_redirect_uri

CTRADER_TOKEN_URL = "https://openapi.ctrader.com/apps/token"
MAX_TOKEN_RESPONSE_BYTES = 64 * 1024


def exchange_authorization_code(
    credentials: CTraderCredentials,
    authorization_code: str,
    redirect_uri: str,
) -> InMemoryTokenProvider:
    """Exchange the short-lived OAuth code for a runtime-only token."""
    if not isinstance(credentials, CTraderCredentials):
        raise ValueError("credentials inválidas")
    if not isinstance(authorization_code, str) or not authorization_code.strip():
        raise ValueError("authorization_code obrigatório")
    if not isinstance(redirect_uri, str) or not redirect_uri.strip():
        raise ValueError("redirect_uri obrigatório")
    _validate_ctrader_redirect_uri(redirect_uri)

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
    with urlopen(request, timeout=15) as response:
        raw = response.read(MAX_TOKEN_RESPONSE_BYTES + 1)
        if len(raw) > MAX_TOKEN_RESPONSE_BYTES:
            raise ValueError("cTrader token response exceeds the allowed size")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("cTrader token response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("cTrader token response is invalid")

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
