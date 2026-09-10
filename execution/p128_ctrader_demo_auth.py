from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode
from typing import Protocol

from execution.p124_broker_session import (
    BrokerSessionObservation,
    BrokerSessionPort,
    BrokerSessionStatus,
)


CTRADER_AUTHORIZATION_URL = "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
CTRADER_TOKEN_URL = "https://openapi.ctrader.com/apps/token"
CTRADER_DEMO_ENDPOINT = "demo.ctraderapi.com:5035"


class CTraderOAuthScope(str, Enum):
    ACCOUNTS = "accounts"
    TRADING = "trading"


@dataclass(frozen=True)
class CTraderOAuthConfig:
    client_id: str
    redirect_uri: str
    scope: CTraderOAuthScope = CTraderOAuthScope.TRADING

    def __post_init__(self) -> None:
        if not isinstance(self.client_id, str) or not self.client_id.strip():
            raise ValueError("client_id obrigatório")
        if not isinstance(self.redirect_uri, str) or not self.redirect_uri.strip():
            raise ValueError("redirect_uri obrigatório")
        if not isinstance(self.scope, CTraderOAuthScope):
            raise ValueError("scope OAuth inválido")

    def authorization_url(self) -> str:
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": self.scope.value,
                "product": "web",
            }
        )
        return f"{CTRADER_AUTHORIZATION_URL}?{query}"


@dataclass(frozen=True)
class CTraderTokenSnapshot:
    """Metadata only; token values must never be persisted in source control."""

    expires_in: int
    has_access_token: bool
    has_refresh_token: bool


class CTraderTokenProvider(Protocol):
    def snapshot(self) -> CTraderTokenSnapshot:
        ...


class CTraderDemoSession(BrokerSessionPort):
    """Adapter-owned session state. Credentials and tokens stay outside the core."""

    def __init__(self, token_provider: CTraderTokenProvider) -> None:
        if token_provider is None:
            raise ValueError("token_provider obrigatório")
        self._token_provider = token_provider

    def check_session(self) -> BrokerSessionObservation:
        try:
            snapshot = self._token_provider.snapshot()
        except Exception as exc:
            return BrokerSessionObservation(
                BrokerSessionStatus.UNAVAILABLE,
                f"falha ao consultar sessão cTrader DEMO: {exc}",
            )

        if not isinstance(snapshot, CTraderTokenSnapshot):
            return BrokerSessionObservation(
                BrokerSessionStatus.UNKNOWN,
                "snapshot de token inválido",
            )
        if not snapshot.has_access_token:
            return BrokerSessionObservation(
                BrokerSessionStatus.UNAVAILABLE,
                "cTrader DEMO sem access token",
            )
        if snapshot.expires_in <= 0:
            return BrokerSessionObservation(
                BrokerSessionStatus.EXPIRED,
                "access token cTrader DEMO expirado",
            )
        return BrokerSessionObservation(
            BrokerSessionStatus.AUTHENTICATED,
            "sessão cTrader DEMO autenticada",
        )
