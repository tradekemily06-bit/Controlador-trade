from datetime import datetime, timezone
import json
from io import BytesIO

import app
from data.models import Candle


def _call(path: str):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path.split("?", 1)[0],
        "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": BytesIO(b""),
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "127.0.0.1:8000",
    }
    body = b"".join(app.application(environ, start_response))
    return captured["status"], json.loads(body)


def test_market_candles_endpoint_serializes_mt5_candles(monkeypatch):
    candles = (
        Candle(datetime(2026, 10, 3, tzinfo=timezone.utc), 1.1, 1.2, 1.0, 1.15, 10),
        Candle(datetime(2026, 10, 3, 0, 5, tzinfo=timezone.utc), 1.15, 1.25, 1.1, 1.2, 12),
    )
    monkeypatch.setattr(app.SERVICE, "get_mt5_market_candles", lambda **_: candles)

    status, payload = _call("/api/market/candles?symbol=EURUSD&timeframe=5m&limit=2")

    assert status.startswith("200")
    assert payload["symbol"] == "EURUSD"
    assert payload["timeframe"] == "5m"
    assert payload["source"] == "IC Markets MT5 DEMO"
    assert len(payload["candles"]) == 2
    assert payload["candles"][0]["close"] == 1.15
    assert payload["candles"][1]["volume"] == 12
