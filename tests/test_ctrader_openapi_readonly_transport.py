from __future__ import annotations

import builtins

import pytest

from integration.ctrader_openapi_readonly_transport import (
    CTraderOpenApiReadOnlyTransport,
)


def test_official_sdk_is_loaded_lazily_and_missing_dependency_fails_closed(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "ctrader_open_api" or name.startswith("ctrader_open_api."):
            raise ImportError("blocked by test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(RuntimeError, match="SDK oficial ausente"):
        CTraderOpenApiReadOnlyTransport(
            client_id="test-client",
            client_secret="test-secret",
            access_token="test-token",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"client_id": "", "client_secret": "secret", "access_token": "token"},
        {"client_id": "client", "client_secret": "", "access_token": "token"},
        {"client_id": "client", "client_secret": "secret", "access_token": ""},
    ],
)
def test_transport_rejects_missing_server_side_credentials(kwargs):
    with pytest.raises(ValueError):
        CTraderOpenApiReadOnlyTransport(**kwargs)


def test_transport_rejects_unsafe_timeout_before_loading_sdk():
    with pytest.raises(ValueError, match="timeout_seconds"):
        CTraderOpenApiReadOnlyTransport(
            client_id="client",
            client_secret="secret",
            access_token="token",
            timeout_seconds=1,
        )
