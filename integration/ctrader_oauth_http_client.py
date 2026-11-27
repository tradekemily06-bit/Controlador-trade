"""TLS-only cTrader OAuth HTTP client.

Spotware documents the token endpoint as an HTTPS REST endpoint. This client
keeps the application secret in memory, never logs request URLs or payloads,
and raises redacted errors so query-string credentials are not echoed.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CTRADER_TOKEN_ENDPOINT = "https://openapi.ctrader.com/apps/token"


class CTraderOAuthHttpClient:
    def __init__(self, *, client_id: str, client_secret: str, timeout_seconds: float = 12.0):
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("cTrader client_id is required")
        if not isinstance(client_secret, str) or not client_secret:
            raise ValueError("cTrader client_secret is required")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 2 <= timeout_seconds <= 30:
            raise ValueError("cTrader OAuth timeout must be between 2 and 30 seconds")
        self._client_id = client_id.strip()
        self._client_secret = client_secret
        self._timeout = float(timeout_seconds)

    def _request(self, *, method: str, parameters: dict[str, str]) -> dict[str, Any]:
        url = f"{CTRADER_TOKEN_ENDPOINT}?{urlencode(parameters)}"
        request = Request(
            url,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read(65537)
        except (HTTPError, URLError, TimeoutError, OSError):
            raise RuntimeError("cTrader OAuth endpoint is unavailable") from None
        if len(raw) > 65536:
            raise RuntimeError("cTrader OAuth response exceeded the size limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("cTrader OAuth endpoint returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise RuntimeError("cTrader OAuth endpoint returned an invalid response")
        if payload.get("errorCode"):
            raise PermissionError("cTrader rejected the OAuth token request")
        access = payload.get("accessToken")
        refresh = payload.get("refreshToken")
        expires = payload.get("expiresIn")
        if not isinstance(access, str) or not access:
            raise RuntimeError("cTrader OAuth response did not contain an access token")
        if refresh is not None and (not isinstance(refresh, str) or not refresh):
            raise RuntimeError("cTrader OAuth response contained an invalid refresh token")
        if isinstance(expires, bool) or not isinstance(expires, int) or not 1 <= expires <= 31536000:
            raise RuntimeError("cTrader OAuth response contained an invalid token lifetime")
        token_type = payload.get("tokenType", "bearer")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise RuntimeError("cTrader OAuth token type is not supported")
        return payload

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip() or len(code) > 4096:
            raise ValueError("cTrader authorization code is invalid")
        if not isinstance(redirect_uri, str) or not redirect_uri.startswith("https://"):
            raise ValueError("cTrader OAuth redirect URI must use HTTPS")
        return self._request(
            method="GET",
            parameters={
                "grant_type": "authorization_code",
                "code": code.strip(),
                "redirect_uri": redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )

    def refresh_tokens(self, refresh_token: str) -> dict[str, Any]:
        if not isinstance(refresh_token, str) or not refresh_token or len(refresh_token) > 16384:
            raise ValueError("cTrader refresh token is invalid")
        return self._request(
            method="POST",
            parameters={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
