import json
from unittest.mock import patch

import pytest

from execution.ctrader_demo_connection import CTraderCredentials
from execution import ctrader_demo_runtime


class _Response:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        if size >= 0:
            return self._payload[:size]
        return self._payload


def test_oauth_exchange_uses_https_post_body_without_secret_in_url():
    credentials = CTraderCredentials("client-123", "super-secret")
    response = _Response(json.dumps({
        "accessToken": "access-token",
        "refreshToken": "refresh-token",
        "expiresIn": 3600,
    }).encode())

    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return response

    with patch.object(ctrader_demo_runtime, "urlopen", fake_urlopen):
        provider = ctrader_demo_runtime.exchange_authorization_code(
            credentials,
            "short-code",
            "https://example.test/callback",
        )

    request = captured["request"]
    assert request.method == "POST"
    assert request.full_url == ctrader_demo_runtime.CTRADER_TOKEN_URL
    assert "super-secret" not in request.full_url
    assert "client-123" not in request.full_url
    assert b"client_secret=super-secret" in request.data
    assert b"client_id=client-123" in request.data
    assert captured["timeout"] == 15
    assert provider.snapshot().has_access_token is True


def test_oauth_exchange_rejects_oversized_response():
    credentials = CTraderCredentials("client-123", "super-secret")
    oversized = b"x" * (ctrader_demo_runtime.MAX_OAUTH_RESPONSE_BYTES + 1)

    with patch.object(
        ctrader_demo_runtime,
        "urlopen",
        return_value=_Response(oversized),
    ):
        with pytest.raises(RuntimeError, match="excede o limite"):
            ctrader_demo_runtime.exchange_authorization_code(
                credentials,
                "short-code",
                "https://example.test/callback",
            )
