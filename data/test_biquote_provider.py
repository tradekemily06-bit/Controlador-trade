from datetime import datetime, timezone
import json

import pytest

from data.biquote_provider import BiQuoteProvider
from data.feed import MarketDataRequest


def _payload():
    return {
        "symbol": "EURUSD",
        "interval": "5m",
        "bars": [
            {
                "openTime": "2026-09-10T18:05:00Z",
                "open": 1.10,
                "high": 1.11,
                "low": 1.09,
                "close": 1.105,
                "tickVolume": 20,
                "isOpen": True,
            },
            {
                "openTime": "2026-09-10T18:00:00Z",
                "open": 1.09,
                "high": 1.10,
                "low": 1.08,
                "close": 1.10,
                "tickVolume": 18,
                "isOpen": False,
            },
        ],
    }


def test_biquote_provider_keeps_only_closed_bars(monkeypatch):
    payload = _payload()
    import data.biquote_provider as module

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size=-1):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: Response())

    result = BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "5m", 10))

    assert len(result) == 1
    assert result[0].close == 1.10
    assert result[0].timestamp == datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)


def test_biquote_provider_rejects_unknown_timeframe():
    with pytest.raises(ValueError, match="unsupported BiQuote timeframe"):
        BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "2m", 10))


def test_biquote_provider_rejects_url_injection_symbol(monkeypatch):
    import data.biquote_provider as module
    called = False

    def fake_open(request, timeout):
        nonlocal called
        called = True
        raise AssertionError("network must not be reached for an invalid symbol")

    monkeypatch.setattr(module, "urlopen", fake_open)
    with pytest.raises(ValueError, match="invalid BiQuote symbol"):
        BiQuoteProvider().fetch(MarketDataRequest("EURUSD/../../secret", "5m", 10))
    assert called is False


def test_biquote_provider_rejects_oversized_response(monkeypatch):
    import data.biquote_provider as module

    class OversizedResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, size=-1):
            return b"x" * (size + 1)

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: OversizedResponse())
    with pytest.raises(ValueError, match="response exceeds"):
        BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "5m", 10))
