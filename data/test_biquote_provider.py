from datetime import datetime, timezone

import pytest

from data.biquote_provider import BiQuoteProvider
from data.feed import MarketDataRequest


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(())


def test_biquote_provider_keeps_only_closed_bars(monkeypatch):
    payload = {
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
        ]
    }

    def fake_urlopen(request, timeout):
        class JsonResponse(FakeResponse):
            def read(self):
                return b""

        import json

        response = JsonResponse(payload)
        original_load = json.load
        response.__class__.json_payload = payload
        return response

    import data.biquote_provider as module

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    Response.payload = payload

    def fake_open(request, timeout):
        class Context:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b""

        context = Context()
        context.payload = payload
        return context

    def fake_json_load(response):
        return response.payload

    monkeypatch.setattr(module, "urlopen", fake_open)
    monkeypatch.setattr(module.json, "load", fake_json_load)

    result = BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "5m", 10))

    assert len(result) == 1
    assert result[0].close == 1.10
    assert result[0].timestamp == datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)


def test_biquote_provider_rejects_unknown_timeframe():
    with pytest.raises(ValueError, match="unsupported BiQuote timeframe"):
        BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "2m", 10))
