from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from wsgiref.simple_server import make_server

from core.signal_engine import SignalEngine

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
ENGINE = SignalEngine()


def _json_response(start_response, status: HTTPStatus, payload: dict) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        f"{status.value} {status.phrase}",
        [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))],
    )
    return [body]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET").upper()

    if path == "/api/health" and method == "GET":
        return _json_response(
            start_response,
            HTTPStatus.OK,
            {"ok": True, "mode": "SIMULACAO", "execution": "bloqueada_por_padrao"},
        )

    if path == "/api/analyze" and method == "POST":
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
            raw = environ["wsgi.input"].read(length)
            data = json.loads(raw or b"{}")
            score = data.get("score", 50)
            confirmed = data.get("confirmed", False)
            filters_ok = data.get("filters_ok", True)
            result = ENGINE.evaluate(
                score=score,
                confirmed=confirmed,
                filters_ok=filters_ok,
                symbol=data.get("symbol"),
                timeframe=data.get("timeframe"),
            )
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {
                    "signal": result.signal.value,
                    "score": result.score,
                    "reason": result.reason,
                    "confirmed": result.confirmed,
                    "symbol": result.symbol,
                    "timeframe": result.timeframe,
                    "execution_allowed": False,
                },
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": f"Entrada inválida: {exc}"})

    if path in {"/", "/index.html"} and method == "GET":
        body = (WEB_DIR / "index.html").read_bytes()
        start_response(
            "200 OK",
            [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))],
        )
        return [body]

    start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"Not Found"]


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    with make_server(host, port, application) as server:
        print(f"Controlador Trading em http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    run()
