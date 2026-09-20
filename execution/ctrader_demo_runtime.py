from __future__ import annotations

import json
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
    """Exchange the short-lived OAuth code without putting secrets in the URL."""
    if not isinstance(credentials, CTraderCredentials):
        raise ValueError("credentials inválidas")
    if not isinstance(authorization_code, str) or not authorization_code.strip():
        raise ValueError("authorization_code obrigatório")
    if not isinstance(redirect_uri, str) or not redirect_uri.strip():
        raise ValueError("redirect_uri obrigatório")

    body = urlencode({
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": redirect_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
    }).encode("utf-8")
    request = Request(
        CTRADER_TOKEN_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise RuntimeError("resposta OAuth inválida")
    if payload.get("errorCode"):
        raise RuntimeError(
            f"cTrader OAuth recusado: {payload.get('description') or payload['errorCode']}"
        )
    if not isinstance(payload.get("accessToken"), str) or not payload["accessToken"].strip():
        raise RuntimeError("OAuth não retornou accessToken")
    if not isinstance(payload.get("expiresIn"), int) or payload["expiresIn"] <= 0:
        raise RuntimeError("OAuth retornou expiresIn inválido")

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
    snapshots = provider.snapshot()
    return snapshots.has_access_token and snapshots.expires_in > 0
