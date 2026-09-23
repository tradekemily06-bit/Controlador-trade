from __future__ import annotations

import hmac
import json
import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from core.api_result import serialize_decision_record
from core.ecosystem_onboarding import EcosystemOnboarding
from core.operational_runtime import build_operational_runtime
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.execution_provider import build_demo_execution_port
from security_guard import MAX_BODY_BYTES, SECURITY
from security_audit import AUDIT

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
RUNTIME_DIR = Path(os.environ.get("CONTROLADOR_RUNTIME_DIR", str(ROOT / ".runtime")))
EXECUTION_PROVIDER = os.environ.get("CONTROLADOR_EXECUTION_PROVIDER", "paper")
EXECUTION_SYMBOL = os.environ.get("CONTROLADOR_EXECUTION_SYMBOL") or None
EXECUTOR = build_demo_execution_port(EXECUTION_PROVIDER, symbol=EXECUTION_SYMBOL)
OPERATIONAL_RUNTIME = build_operational_runtime(RUNTIME_DIR, executor=EXECUTOR)
SERVICE = ConfiguredEcosystemService(operational_runtime=OPERATIONAL_RUNTIME)
ONBOARDING = EcosystemOnboarding()


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


def _authorize_internal_update(environ) -> tuple[bool, str]:
    expected = os.environ.get("CONTROLADOR_UPDATE_TOKEN", "").strip()
    if not expected:
        return False, "internal update endpoint is not configured"
    provided = str(environ.get("HTTP_AUTHORIZATION", ""))
    if not provided.startswith("Bearer "):
        return False, "internal authorization required"
    token = provided[7:].strip()
    if not token or not hmac.compare_digest(token, expected):
        return False, "internal authorization denied"
    return True, "authorized"


def _file_response(start_response, path: Path, content_type: str, request_id: str, environ) -> list[bytes]:
    body = path.read_bytes()
    script_nonce = SECURITY.script_nonce() if content_type.startswith("text/html") else None
    if script_nonce:
        body = body.replace(b"<script>", f'<script nonce="{script_nonce}">'.encode("ascii"), 1)
        if path == WEB_DIR / "index.html":
            notification_html = (WEB_DIR / "components" / "notifications.html").read_text(encoding="utf-8").encode("utf-8")
            notification_js = (WEB_DIR / "components" / "notifications.js").read_text(encoding="utf-8")
            onboarding_html = (WEB_DIR / "components" / "onboarding.html").read_text(encoding="utf-8").encode("utf-8")
            onboarding_js = (WEB_DIR / "components" / "onboarding.js").read_text(encoding="utf-8")
            notification_script = f'<script nonce="{script_nonce}">{notification_js}</script>'.encode("utf-8")
            onboarding_script = f'<script nonce="{script_nonce}">{onboarding_js}</script>'.encode("utf-8")
            notification_mount = notification_html + notification_script
            onboarding_mount = onboarding_html + onboarding_script
            anchor = '<div class="section">Visão geral</div>'.encode("utf-8")
            body = body.replace(anchor, notification_mount + onboarding_mount + anchor, 1)
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
        if path == "/api/onboarding" and method == "GET":
            guide = ONBOARDING.build_first_use_guide()
            return _json_response(start_response, HTTPStatus.OK, {"guide": {"guide_id": guide.guide_id, "title": guide.title, "steps": [{"step_id": step.step_id, "title": step.title, "purpose": step.purpose, "location": step.location.value, "action_hint": step.action_hint, "technical_details_hidden": step.technical_details_hidden} for step in guide.steps], "completion_message": guide.completion_message, "execution_authorized": guide.execution_authorized}}, request_id, environ)
        if path == "/api/preferences" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.get_preferences()}, request_id, environ)
        if path == "/api/preferences" and method == "POST":
            return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.update_preferences(_read_json(environ))}, request_id, environ)
        if path == "/api/preferences/candles" and method == "POST":
            return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.update_candle_preferences(_read_json(environ))}, request_id, environ)
        if path == "/api/preferences/notifications" and method == "POST":
            return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.update_notification_preferences(_read_json(environ))}, request_id, environ)
        if path == "/api/notifications" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.notification_summary(), request_id, environ)
        if path == "/api/notifications/all" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"items": SERVICE.all_notifications()}, request_id, environ)
        if path == "/api/updates" and method == "POST":
            authorized, reason = _authorize_internal_update(environ)
            if not authorized:
                status = HTTPStatus.SERVICE_UNAVAILABLE if reason == "internal update endpoint is not configured" else HTTPStatus.FORBIDDEN
                return _json_response(start_response, status, {"error": reason, "request_id": request_id}, request_id, environ)
            data = _read_json(environ)
            item = SERVICE.publish_ecosystem_update(str(data.get("title", "")), str(data.get("message", "")))
            return _json_response(start_response, HTTPStatus.OK, {"notification": item}, request_id, environ)
        if path == "/api/saas/status" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.saas_status(), request_id, environ)
        if path == "/api/analyze" and method == "POST":
            record = SERVICE.analyze(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {**record.to_dict(), **serialize_decision_record(record), "execution_allowed": False}, request_id, environ)
        if path == "/api/demo/execute" and method == "POST":
            data = _read_json(environ)
            result = SERVICE.execute_demo(
                symbol=str(data.get("symbol", "")),
                signal=str(data.get("signal", "")),
                amount=data.get("amount", 0),
                duration_seconds=data.get("duration_seconds", 60),
                request_id=data.get("request_id"),
            )
            return _json_response(start_response, HTTPStatus.OK, result, request_id, environ)
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
        if path == "/api/learning/sources" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, {"sources": SERVICE.learning_sources_view(), "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/sources/screen" and method == "POST":
            source = SERVICE.screen_learning_source(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {"source": {**source.__dict__, "source_type": source.source_type.value, "status": source.status.value}, "operation_eligible": False}, request_id, environ)
        if path == "/api/learning/sources/validate" and method == "POST":
            data = _read_json(environ)
            source = SERVICE.learning_sources.get(str(data.get("source_id", "")))
            if source is None:
                raise ValueError("source_id não encontrado")
            updated = SERVICE.validate_learning_source(source, content_verified=bool(data.get("content_verified", False)), security_checked=bool(data.get("security_checked", False)))
            return _json_response(start_response, HTTPStatus.OK, {"source": {**updated.__dict__, "source_type": updated.source_type.value, "status": updated.status.value}, "operation_eligible": False}, request_id, environ)
        if path == "/api/learning/sources/admit" and method == "POST":
            data = _read_json(environ)
            source = SERVICE.learning_sources.get(str(data.get("source_id", "")))
            if source is None:
                raise ValueError("source_id não encontrado")
            updated = SERVICE.admit_learning_knowledge(source, knowledge_validated=bool(data.get("knowledge_validated", False)))
            return _json_response(start_response, HTTPStatus.OK, {"source": {**updated.__dict__, "source_type": updated.source_type.value, "status": updated.status.value}, "operation_eligible": False}, request_id, environ)
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
        if path == "/api/learning/professor/activity" and method == "POST":
            activity = SERVICE.generate_professor_activity(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {"activity": activity.__dict__, "execution_allowed": False, "learning_authorizes_trading": False}, request_id, environ)
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
