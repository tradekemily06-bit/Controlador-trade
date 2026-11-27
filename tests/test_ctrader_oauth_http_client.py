import json
from unittest.mock import patch

import pytest

from integration.ctrader_oauth_http_client import CTraderOAuthHttpClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.payload


def test_exchange_code_uses_https_spotware_endpoint_and_redacts_errors():
    client = CTraderOAuthHttpClient(client_id="client-id", client_secret="private-secret")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.method
        seen["timeout"] = timeout
        return FakeResponse({
            "accessToken": "access", "refreshToken": "refresh",
            "expiresIn": 2628000, "tokenType": "bearer", "errorCode": None,
        })

    with patch("integration.ctrader_oauth_http_client.urlopen", fake_urlopen):
        result = client.exchange_code("short-code", "https://app.example.com/ctrader/callback")
    assert result["accessToken"] == "access"
    assert seen["url"].startswith("https://openapi.ctrader.com/apps/token?")
    assert "client_secret=private-secret" in seen["url"]
    assert seen["method"] == "GET"


def test_refresh_uses_post_and_rotates_refresh_token():
    client = CTraderOAuthHttpClient(client_id="client-id", client_secret="private-secret")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["method"] = request.method
        seen["url"] = request.full_url
        return FakeResponse({
            "accessToken": "new-access", "refreshToken": "new-refresh",
            "expiresIn": 2628000, "tokenType": "bearer", "errorCode": None,
        })

    with patch("integration.ctrader_oauth_http_client.urlopen", fake_urlopen):
        result = client.refresh_tokens("old-refresh")
    assert seen["method"] == "POST"
    assert "grant_type=refresh_token" in seen["url"]
    assert result["refreshToken"] == "new-refresh"


def test_oauth_provider_error_is_redacted():
    client = CTraderOAuthHttpClient(client_id="client-id", client_secret="private-secret")
    with patch(
        "integration.ctrader_oauth_http_client.urlopen",
        lambda request, timeout: FakeResponse({
            "errorCode": "invalid_grant", "description": "sensitive-reflected-value"
        }),
    ):
        with pytest.raises(PermissionError) as error:
            client.exchange_code("code", "https://app.example.com/callback")
    assert "sensitive-reflected-value" not in str(error.value)
    assert "private-secret" not in str(error.value)
