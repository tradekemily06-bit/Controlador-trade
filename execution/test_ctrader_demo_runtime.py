from urllib.error import HTTPError

import pytest

from execution.ctrader_demo_connection import CTraderCredentials
import execution.ctrader_demo_runtime as runtime


def test_oauth_transport_error_does_not_expose_secret(monkeypatch):
    secret = "SUPER-SECRET"
    credentials = CTraderCredentials("client", secret)

    def fail(*args, **kwargs):
        raise HTTPError(
            "https://openapi.ctrader.com/apps/token?client_secret=" + secret,
            401,
            "unauthorized",
            {},
            None,
        )

    monkeypatch.setattr(runtime, "urlopen", fail)

    with pytest.raises(RuntimeError) as exc:
        runtime.exchange_authorization_code(credentials, "code", "https://example.test/callback")

    assert secret not in str(exc.value)
    assert "SUPER-SECRET" not in repr(exc.value)
