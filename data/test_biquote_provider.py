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
    with pytest.raises(ValueError, match="Timeframe"):
        BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "M0", 10))



def test_biquote_provider_builds_only_complete_aligned_ten_minute_candles(monkeypatch):
    import data.biquote_provider as module

    payload = {
        "bars": [
            {
                "openTime": f"2026-09-10T18:{minute:02d}:00Z",
                "open": opening,
                "high": high,
                "low": low,
                "close": closing,
                "tickVolume": volume,
                "isOpen": False,
            }
            for minute, opening, high, low, closing, volume in [
                (0, 1.10, 1.12, 1.09, 1.11, 10),
                (5, 1.11, 1.13, 1.10, 1.12, 12),
                (10, 1.12, 1.14, 1.11, 1.13, 8),
                (15, 1.13, 1.15, 1.12, 1.14, 9),
            ]
        ]
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(request, timeout):
        return Response()

    monkeypatch.setattr(module, "urlopen", fake_open)
    monkeypatch.setattr(module.json, "load", lambda response: payload)

    result = BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "10m", 2))

    assert len(result) == 2
    assert result[0].timestamp == datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)
    assert result[0].open == 1.10
    assert result[0].high == 1.13
    assert result[0].low == 1.09
    assert result[0].close == 1.12
    assert result[0].volume == 22
    assert result[1].timestamp == datetime(2026, 9, 10, 18, 10, tzinfo=timezone.utc)



@pytest.mark.parametrize(
    ("timeframe", "source_interval", "timestamps"),
    [
        ("2m", "1m", [0, 60]),
        ("20m", "5m", [0, 300, 600, 900]),
        ("2h", "1h", [0, 3600]),
        ("1w", "1d", [0, 86400, 172800, 259200, 345600, 432000, 518400]),
    ],
)
def test_biquote_provider_aggregates_variable_timeframes(
    monkeypatch, timeframe, source_interval, timestamps
):
    import data.biquote_provider as module

    base = datetime(2026, 9, 7, tzinfo=timezone.utc)
    payload = {
        "bars": [
            {
                "openTime": (base + __import__("datetime").timedelta(seconds=offset)).isoformat().replace("+00:00", "Z"),
                "open": 1.0 + index,
                "high": 1.2 + index,
                "low": 0.8 + index,
                "close": 1.1 + index,
                "tickVolume": 10 + index,
                "isOpen": False,
            }
            for index, offset in enumerate(timestamps)
        ]
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: Response())
    monkeypatch.setattr(module.json, "load", lambda response: payload)

    result = BiQuoteProvider().fetch(MarketDataRequest("EURUSD", timeframe, 2))

    assert len(result) == 1
    assert result[0].open == 1.0
    assert result[0].high == 1.2 + len(timestamps) - 1
    assert result[0].low == 0.8
    assert result[0].close == 1.1 + len(timestamps) - 1
    assert result[0].volume == sum(10 + index for index in range(len(timestamps)))


def test_biquote_provider_discards_incomplete_custom_timeframe_bucket(monkeypatch):
    import data.biquote_provider as module

    payload = {
        "bars": [
            {
                "openTime": f"2026-09-07T00:{minute:02d}:00Z",
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.05,
                "tickVolume": 10,
                "isOpen": False,
            }
            for minute in (0, 5, 10)
        ]
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: Response())
    monkeypatch.setattr(module.json, "load", lambda response: payload)

    result = BiQuoteProvider().fetch(MarketDataRequest("EURUSD", "20m", 2))

    assert result == []
