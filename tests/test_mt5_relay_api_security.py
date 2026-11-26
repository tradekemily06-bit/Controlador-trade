from standalone_app import _mt5_relay_authorized


def test_mt5_relay_requires_secret_and_tls(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_MT5_RELAY_TOKEN", "a-long-test-token")
    monkeypatch.delenv("CONTROLADOR_TRUST_PROXY_TLS", raising=False)

    assert not _mt5_relay_authorized({
        "HTTP_AUTHORIZATION": "Bearer a-long-test-token",
        "wsgi.url_scheme": "http",
    })
    assert _mt5_relay_authorized({
        "HTTP_AUTHORIZATION": "Bearer a-long-test-token",
        "wsgi.url_scheme": "https",
    })


def test_mt5_relay_accepts_tls_terminated_by_explicitly_trusted_proxy(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_MT5_RELAY_TOKEN", "a-long-test-token")
    monkeypatch.setenv("CONTROLADOR_TRUST_PROXY_TLS", "true")

    assert _mt5_relay_authorized({
        "HTTP_AUTHORIZATION": "Bearer a-long-test-token",
        "wsgi.url_scheme": "http",
        "HTTP_X_FORWARDED_PROTO": "https",
    })
    assert not _mt5_relay_authorized({
        "HTTP_AUTHORIZATION": "Bearer wrong-token",
        "wsgi.url_scheme": "https",
    })
