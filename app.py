from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from wsgiref.simple_server import make_server

from integration.ecosystem_service import EcosystemService

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
SERVICE = EcosystemService()


def _json_response(start_response, status: HTTPStatus, payload: dict) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(f"{status.value} {status.phrase}", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))])
    return [body]


def _read_json(environ) -> dict:
    length = int(environ.get("CONTENT_LENGTH") or "0")
    raw = environ["wsgi.input"].read(length)
    data = json.loads(raw or b"{}")
    if not isinstance(data, dict):
        raise ValueError("payload deve ser um objeto JSON")
    return data


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET").upper()
    try:
        if path == "/api/health" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"ok": True, **SERVICE.system_status()})
        if path == "/api/status" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.system_status())
        if path == "/api/analyze" and method == "POST":
            record = SERVICE.analyze(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {**record.to_dict(), "execution_allowed": False})
        if path == "/api/replay" and method == "POST":
            cases = _read_json(environ).get("cases")
            if not isinstance(cases, list):
                raise ValueError("cases deve ser uma lista")
            return _json_response(start_response, HTTPStatus.OK, {"results": SERVICE.replay(cases), "execution_allowed": False})
        if path == "/api/memory" and method == "GET":
            query = environ.get("QUERY_STRING") or "limit=50"
            limit = int(query.split("limit=")[-1].split("&")[0])
            return _json_response(start_response, HTTPStatus.OK, {"records": SERVICE.memory_view(limit)})
        if path == "/api/statistics" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.statistics())
        if path == "/api/outcome" and method == "POST":
            data = _read_json(environ)
            record = SERVICE.record_outcome(str(data.get("decision_id", "")), str(data.get("outcome", "")))
            return _json_response(start_response, HTTPStatus.OK, record.to_dict())
        if path == "/api/risk" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.risk_status())
        if path == "/api/news" and method == "GET":
            query = environ.get("QUERY_STRING") or "limit=10"
            limit = int(query.split("limit=")[-1].split("&")[0])
            return _json_response(start_response, HTTPStatus.OK, SERVICE.news_status(limit))
        if path == "/api/connections" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.connections())
        if path in {"/", "/index.html"} and method == "GET":
            body = (WEB_DIR / "index.html").read_bytes()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": f"Entrada inválida: {exc}"})
    start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"Not Found"]


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    with make_server(host, port, application) as server:
        print(f"Controlador Trading em http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    run()
