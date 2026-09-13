from __future__ import annotations

import json
import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from core.api_result import serialize_decision_record
from integration.ecosystem_service import EcosystemService
from security_guard import MAX_BODY_BYTES, SECURITY
from security_audit import AUDIT

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
SERVICE = EcosystemService()


def _audit(environ, request_id: str, status: int) -> None:
    AUDIT.record(request_id=request_id, method=str(environ.get("REQUEST_METHOD", "GET")).upper(), path=str(environ.get("PATH_INFO", "/")), status=status, client_key=SECURITY.client_key(environ))


def _json_response(start_response, status: HTTPStatus, payload: dict, request_id: str, environ=None) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))]
    headers.extend(SECURITY.headers(request_id))
    start_response(f"{status.value} {status.phrase}", headers)
    if environ is not None:
        _audit(environ, request_id, status.value)
    return [body]


def _read_json(environ) -> dict:
    raw_length = environ.get("CONTENT_LENGTH") or "0"
    try:
        length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("content-length inválido") from exc
    if length < 0 or length > MAX_BODY_BYTES:
        raise ValueError("payload excede o limite permitido")
    raw = environ["wsgi.input"].read(length)
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("payload excede o limite permitido")
    data = json.loads(raw or b"{}")
    if not isinstance(data, dict):
        raise ValueError("payload deve ser um objeto JSON")
    return data


def _query_limit(environ, default: int, maximum: int = 100) -> int:
    values = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True).get("limit")
    if not values or values[-1] == "":
        return default
    limit = int(values[-1])
    if not 1 <= limit <= maximum:
        raise ValueError(f"limit deve estar entre 1 e {maximum}")
    return limit


def _file_response(start_response, path: Path, content_type: str, request_id: str, environ) -> list[bytes]:
    body = path.read_bytes()
    script_nonce = SECURITY.script_nonce() if content_type.startswith("text/html") else None
    if script_nonce:
        body = body.replace(b"<script>", f'<script nonce="{script_nonce}">'.encode("ascii"), 1)
    headers = [("Content-Type", content_type), ("Content-Length", str(len(body)))]
    headers.extend(SECURITY.headers(request_id, script_nonce=script_nonce))
    start_response("200 OK", headers)
    _audit(environ, request_id, 200)
    return [body]


def application(environ, start_response):
    request_id = SECURITY.request_id()
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET").upper()
    if not SECURITY.allow(environ):
        return _json_response(start_response, HTTPStatus.TOO_MANY_REQUESTS, {"error": "Limite de requisições excedido", "request_id": request_id}, request_id, environ)

    try:
        if path == "/api/health" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"ok": True, **SERVICE.system_status()}, request_id, environ)
        if path == "/api/status" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.system_status(), request_id, environ)
        if path == "/api/saas/status" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.saas_status(), request_id, environ)
        if path == "/api/analyze" and method == "POST":
            record = SERVICE.analyze(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {**record.to_dict(), **serialize_decision_record(record), "execution_allowed": False}, request_id, environ)
        if path == "/api/replay" and method == "POST":
            cases = _read_json(environ).get("cases")
            if not isinstance(cases, list):
                raise ValueError("cases deve ser uma lista")
            return _json_response(start_response, HTTPStatus.OK, {"results": SERVICE.replay(cases), "execution_allowed": False}, request_id, environ)
        if path == "/api/memory" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"records": SERVICE.memory_view(_query_limit(environ, 50))}, request_id, environ)
        if path == "/api/statistics" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.statistics(), request_id, environ)
        if path == "/api/outcome" and method == "POST":
            data = _read_json(environ)
            record = SERVICE.record_outcome(str(data.get("decision_id", "")), str(data.get("outcome", "")))
            return _json_response(start_response, HTTPStatus.OK, record.to_dict(), request_id, environ)
        if path == "/api/risk" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.risk_status(), request_id, environ)
        if path == "/api/news" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.news_status(_query_limit(environ, 10)), request_id, environ)
        if path == "/api/connections" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.connections(), request_id, environ)
        if path == "/api/learning" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.learning_summary(), request_id, environ)
        if path == "/api/learning/resources" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"resources": SERVICE.learning_resources_view(), "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/resources" and method == "POST":
            resource = SERVICE.add_learning_resource(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {"resource": {**resource.__dict__, "content_type": resource.content_type.value, "status": resource.status.value}, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/observations" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"observations": SERVICE.learning_observations_view(), "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/observations" and method == "POST":
            observation = SERVICE.add_learning_observation(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {"observation": observation.__dict__, "execution_allowed": False, "learning_authorizes_trading": False}, request_id, environ)
        if path == "/api/learning/activities" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"activities": SERVICE.learning_activities_view(), "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/activities" and method == "POST":
            activity = SERVICE.add_learning_activity(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {"activity": activity.__dict__, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/attempts" and method == "POST":
            attempt = SERVICE.add_learning_attempt(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {"attempt": attempt.__dict__, "execution_allowed": False}, request_id, environ)
        if path in {"/", "/index.html"} and method == "GET":
            return _file_response(start_response, WEB_DIR / "index.html", "text/html; charset=utf-8", request_id, environ)
        if path == "/manifest.webmanifest" and method == "GET":
            return _file_response(start_response, WEB_DIR / "manifest.webmanifest", "application/manifest+json; charset=utf-8", request_id, environ)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Entrada inválida", "request_id": request_id}, request_id, environ)

    headers = [("Content-Type", "text/plain; charset=utf-8")]
    headers.extend(SECURITY.headers(request_id))
    start_response("404 Not Found", headers)
    _audit(environ, request_id, 404)
    return [b"Not Found"]


def run(host: str = "0.0.0.0", port: int | None = None) -> None:
    selected_port = port or int(os.environ.get("PORT", "8000"))
    with make_server(host, selected_port, application) as server:
        print(f"Controlador Trading em http://{host}:{selected_port}")
        server.serve_forever()


if __name__ == "__main__":
    run()
