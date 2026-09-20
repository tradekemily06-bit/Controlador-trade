from __future__ import annotations

import json
from types import SimpleNamespace

from execution.ctrader_demo_connection import CTraderCredentials
from execution import ctrader_demo_runtime


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({
            "accessToken": "runtime-token",
            "expiresIn": 3600,
            "refreshToken": "runtime-refresh",
        }).encode("utf-8")


def test_ctrader_token_exchange_uses_post_body_and_never_puts_secret_in_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(ctrader_demo_runtime, "urlopen", fake_urlopen)

    credentials = CTraderCredentials("client-123", "super-secret")
    provider = ctrader_demo_runtime.exchange_authorization_code(
        credentials,
        "auth-code",
        "https://example.test/callback",
    )

    request = captured["request"]
    assert request.full_url == ctrader_demo_runtime.CTRADER_TOKEN_URL
    assert request.method == "POST"
    assert request.data is not None
    body = request.data.decode("utf-8")
    assert "client_secret=super-secret" in body
    assert "super-secret" not in request.full_url
    assert provider.access_token == "runtime-token"
    assert captured["timeout"] == 15
