from io import BytesIO
import json

import app


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


def test_market_assets_endpoint_exposes_session_and_247_evidence(monkeypatch):
    assets = (
        {
            "symbol": "BTCUSD",
            "asset_class": "crypto",
            "visible": True,
            "tradeable": True,
            "quote_available": True,
            "weekend_capable": True,
            "state": "OPEN",
            "reason": "símbolo disponível para análise",
            "is_24_7_capable": True,
            "suitability": "WATCH",
            "suitability_evidence": ["sessão aberta confirmada"],
            "suitability_gaps": [],
            "suitability_rationale": "acompanhamento",
            "source": "IC Markets MT5 DEMO",
        },
    )
    monkeypatch.setattr(app.SERVICE, "get_mt5_assets", lambda **_: assets)

    status, payload = _call("/api/market/assets")

    assert status.startswith("200")
    assert payload["source"] == "IC Markets MT5 DEMO"
    assert payload["count"] == 1
    assert payload["assets"][0]["symbol"] == "BTCUSD"
    assert payload["assets"][0]["is_24_7_capable"] is True
