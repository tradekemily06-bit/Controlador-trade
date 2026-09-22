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
from execution.mt5_demo_risk_state_provider import MT5DemoRiskStateConfig, MT5DemoRiskStateProvider
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.execution_provider import build_demo_execution_port
from security_guard import MAX_BODY_BYTES, SECURITY
from security_audit import AUDIT
from security.http_identity import PublicSaaSNotReady, require_role, require_tenant_scoped_data_plane, require_trusted_identity, saas_public_mode

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
RUNTIME_DIR = Path(os.environ.get("CONTROLADOR_RUNTIME_DIR", str(ROOT / ".runtime")))
EXECUTION_PROVIDER = os.environ.get("CONTROLADOR_EXECUTION_PROVIDER", "paper")
EXECUTION_SYMBOL = os.environ.get("CONTROLADOR_EXECUTION_SYMBOL") or None


def _build_authoritative_risk_provider():
    if EXECUTION_PROVIDER != "ic_markets_mt5_demo":
        return None
    raw_timeframe = os.environ.get("CONTROLADOR_EXECUTION_TIMEFRAME", "5").strip()
    try:
        timeframe = int(raw_timeframe)
    except ValueError as exc:
        raise RuntimeError("CONTROLADOR_EXECUTION_TIMEFRAME must be an integer for MT5 DEMO") from exc
    if timeframe <= 0:
        raise RuntimeError("CONTROLADOR_EXECUTION_TIMEFRAME must be greater than zero for MT5 DEMO")
    return MT5DemoRiskStateProvider(MT5DemoRiskStateConfig(symbol=EXECUTION_SYMBOL, timeframe=timeframe))


RISK_STATE_PROVIDER = _build_authoritative_risk_provider()
if EXECUTION_PROVIDER == "paper":
    OPERATIONAL_RUNTIME = build_operational_runtime(RUNTIME_DIR)
else:
    EXECUTOR = build_demo_execution_port(EXECUTION_PROVIDER, symbol=EXECUTION_SYMBOL)
    OPERATIONAL_RUNTIME = build_operational_runtime(
        RUNTIME_DIR,
        executor=EXECUTOR,
        risk_state_provider=RISK_STATE_PROVIDER,
    )
SERVICE = ConfiguredEcosystemService(operational_runtime=OPERATIONAL_RUNTIME)
ONBOARDING = EcosystemOnboarding()
PUBLIC_SAAS_MUTATIONS = {"/api/preferences", "/api/preferences/candles", "/api/preferences/notifications", "/api/analyze", "/api/replay", "/api/outcome", "/api/psychology/check-in", "/api/psychology/advanced", "/api/learning/resources", "/api/learning/sources/screen", "/api/learning/sources/validate", "/api/learning/sources/admit", "/api/learning/observations", "/api/learning/activities", "/api/learning/professor/activity", "/api/learning/attempts"}
PUBLIC_SAAS_READS = {"/api/status", "/api/preferences", "/api/notifications", "/api/notifications/all", "/api/memory", "/api/statistics", "/api/risk", "/api/news", "/api/connections", "/api/learning", "/api/learning/resources", "/api/learning/sources", "/api/learning/observations", "/api/learning/activities", "/api/psychology/status", "/api/saas/status"}
ADMIN_ONLY_SAAS_MUTATIONS = {"/api/learning/sources/validate", "/api/learning/sources/admit"}


def _audit(environ, request_id: str, status: int) -> None:
    AUDIT.record(request_id=request_id, method=str(environ.get("REQUEST_METHOD", "GET")).upper(), path=str(environ.get("PATH_INFO", "/")), status=status, client_key=SECURITY.client_key(environ))


def _json_response(start_response, status: HTTPStatus, payload: dict, request_id: str, environ=None) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))] + SECURITY.headers(request_id)
    start_response(f"{status.value} {status.phrase}", headers)
    if environ is not None:
        _audit(environ, request_id, status.value)
    return [body]


def _text_response(start_response, status: HTTPStatus, body: bytes, request_id: str, environ=None) -> list[bytes]:
    headers = [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))] + SECURITY.headers(request_id)
    start_response(f"{status.value} {status.phrase}", headers)
    if environ is not None:
        _audit(environ, request_id, status.value)
    return [body]


def _read_json(environ) -> dict:
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except (TypeError, ValueError) as exc:
        raise ValueError("Entrada inválida: content-length inválido") from exc
    if length < 0 or length > MAX_BODY_BYTES:
        raise ValueError("Entrada inválida: payload excede o limite permitido")
    raw = environ["wsgi.input"].read(length)
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("Entrada inválida: payload excede o limite permitido")
    try:
        data = json.loads(raw or b"{}")
    except (TypeError, ValueError) as exc:
        raise ValueError("Entrada inválida: JSON inválido") from exc
    if not isinstance(data, dict):
        raise ValueError("Entrada inválida: payload deve ser um objeto JSON")
    return data


def _query_limit(environ, default: int, maximum: int = 100) -> int:
    values = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True).get("limit")
    if not values or values[-1] == "":
        return default
    try:
        limit = int(values[-1])
    except (TypeError, ValueError) as exc:
        raise ValueError("limit deve ser um inteiro") from exc
    if limit < 1:
        raise ValueError("limit deve ser maior que zero")
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


def _authorize_public_saas_request(environ, path: str, method: str) -> None:
    if not saas_public_mode():
        return
    if method == "POST" and path in PUBLIC_SAAS_MUTATIONS:
        identity = require_trusted_identity(environ)
        if path in ADMIN_ONLY_SAAS_MUTATIONS:
            require_role(identity, "admin")
        require_tenant_scoped_data_plane()
    elif method == "GET" and path in PUBLIC_SAAS_READS:
        require_trusted_identity(environ)
        require_tenant_scoped_data_plane()


def _file_response(start_response, path: Path, content_type: str, request_id: str, environ) -> list[bytes]:
    body = path.read_bytes()
    script_nonce = SECURITY.script_nonce() if content_type.startswith("text/html") else None
    if script_nonce:
        body = body.replace(b"<script>", f'<script nonce="{script_nonce}">'.encode("ascii"), 1)
        if path == WEB_DIR / "index.html":
            notification_html = (WEB_DIR / "components" / "notifications.html").read_text(encoding="utf-8")
            notification_js = (WEB_DIR / "components" / "notifications.js").read_text(encoding="utf-8")
            onboarding_html = (WEB_DIR / "components" / "onboarding.html").read_text(encoding="utf-8")
            onboarding_js = (WEB_DIR / "components" / "onboarding.js").read_text(encoding="utf-8")
            notification_script = f'<script nonce="{script_nonce}">{notification_js}</script>'
            onboarding_script = f'<script nonce="{script_nonce}">{onboarding_js}</script>'
            notification_mount = (notification_html + notification_script).encode("utf-8")
            onboarding_mount = (onboarding_html + onboarding_script).encode("utf-8")
            anchor = '<div class="section">Visão geral</div>'.encode("utf-8")
            body = body.replace(anchor, notification_mount + onboarding_mount + anchor, 1)
    headers = [("Content-Type", content_type), ("Content-Length", str(len(body)))] + SECURITY.headers(request_id, script_nonce=script_nonce)
    start_response("200 OK", headers)
    _audit(environ, request_id, 200)
    return [body]


def _learning_source_for_request(source_id: str):
    wanted = str(source_id).strip()
    for item in SERVICE.learning_sources_view():
        if str(item.get("source_id", "")) == wanted:
            from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType
            return LearningSource(source_id=wanted, source_type=LearningSourceType(str(item["source_type"]).upper()), uri=str(item["uri"]), status=LearningSourceStatus(str(item["status"]).upper()), content_verified=bool(item.get("content_verified", False)), security_checked=bool(item.get("security_checked", False)), knowledge_validated=bool(item.get("knowledge_validated", False)), operation_eligible=False)
    raise ValueError("source_id não encontrado")


def application(environ, start_response):
    request_id = SECURITY.request_id(); path = environ.get("PATH_INFO", "/"); method = environ.get("REQUEST_METHOD", "GET").upper()
    if not SECURITY.allow(environ):
        return _json_response(start_response, HTTPStatus.TOO_MANY_REQUESTS, {"error": "Limite de requisições excedido", "request_id": request_id}, request_id, environ)
    try:
        _authorize_public_saas_request(environ, path, method)
        identity = require_trusted_identity(environ) if saas_public_mode() else None
        owner_kwargs = {"subject_id": identity.subject_id, "tenant_id": identity.tenant_id} if identity is not None else {}
        if path == "/api/health" and method == "GET": return _json_response(start_response, HTTPStatus.OK, {"ok": True} if saas_public_mode() else {"ok": True, **SERVICE.system_status()}, request_id, environ)
        if path == "/api/status" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.public_status() if saas_public_mode() else SERVICE.system_status(), request_id, environ)
        if path == "/api/onboarding" and method == "GET":
            guide = ONBOARDING.build_first_use_guide(); return _json_response(start_response, HTTPStatus.OK, {"guide": {"guide_id": guide.guide_id, "title": guide.title, "steps": [{"step_id": step.step_id, "title": step.title, "purpose": step.purpose, "location": step.location.value, "action_hint": step.action_hint, "technical_details_hidden": step.technical_details_hidden} for step in guide.steps], "completion_message": guide.completion_message, "execution_authorized": guide.execution_authorized}}, request_id, environ)
        if path == "/api/preferences" and method == "GET": return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.get_preferences()}, request_id, environ)
        if path == "/api/preferences" and method == "POST": return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.update_preferences(_read_json(environ))}, request_id, environ)
        if path == "/api/preferences/candles" and method == "POST": return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.update_candle_preferences(_read_json(environ))}, request_id, environ)
        if path == "/api/preferences/notifications" and method == "POST": return _json_response(start_response, HTTPStatus.OK, {"preferences": SERVICE.update_notification_preferences(_read_json(environ))}, request_id, environ)
        if path == "/api/notifications" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.notification_summary(), request_id, environ)
        if path == "/api/notifications/all" and method == "GET": return _json_response(start_response, HTTPStatus.OK, {"items": SERVICE.all_notifications()}, request_id, environ)
        if path == "/api/updates" and method == "POST":
            authorized, reason = _authorize_internal_update(environ)
            if not authorized:
                status = HTTPStatus.SERVICE_UNAVAILABLE if reason == "internal update endpoint is not configured" else HTTPStatus.FORBIDDEN
                return _json_response(start_response, status, {"error": reason, "request_id": request_id}, request_id, environ)
            data = _read_json(environ); item = SERVICE.publish_ecosystem_update(str(data.get("title", "")), str(data.get("message", ""))); return _json_response(start_response, HTTPStatus.OK, {"notification": item}, request_id, environ)
        if path == "/api/saas/status" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.saas_status(), request_id, environ)
        if path == "/api/psychology/status" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.psychology_status(), request_id, environ)
        if path == "/api/psychology/check-in" and method == "POST": return _json_response(start_response, HTTPStatus.OK, SERVICE.psychology_check_in(_read_json(environ)), request_id, environ)
        if path == "/api/psychology/advanced" and method == "POST": return _json_response(start_response, HTTPStatus.OK, SERVICE.advanced_psychology_assessment(_read_json(environ)), request_id, environ)
        if path == "/api/analyze" and method == "POST":
            record = SERVICE.analyze(_read_json(environ), **owner_kwargs); return _json_response(start_response, HTTPStatus.OK, {**record.to_dict(), **serialize_decision_record(record), "execution_allowed": False}, request_id, environ)
        if path == "/api/replay" and method == "POST":
            cases = _read_json(environ).get("cases")
            if not isinstance(cases, list): raise ValueError("cases deve ser uma lista")
            return _json_response(start_response, HTTPStatus.OK, {"results": SERVICE.replay(cases, **owner_kwargs), "execution_allowed": False}, request_id, environ)
        if path == "/api/memory" and method == "GET": return _json_response(start_response, HTTPStatus.OK, {"records": SERVICE.memory_view(_query_limit(environ, 50), **owner_kwargs)}, request_id, environ)
        if path == "/api/statistics" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.statistics(**owner_kwargs), request_id, environ)
        if path == "/api/outcome" and method == "POST":
            data = _read_json(environ); record = SERVICE.record_outcome(str(data.get("decision_id", "")), str(data.get("outcome", "")), **owner_kwargs); return _json_response(start_response, HTTPStatus.OK, record.to_dict(), request_id, environ)
        if path == "/api/risk" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.risk_status(), request_id, environ)
        if path == "/api/news" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.news_status(_query_limit(environ, 10)), request_id, environ)
        if path == "/api/connections" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.connections(), request_id, environ)
        if path == "/api/learning" and method == "GET": return _json_response(start_response, HTTPStatus.OK, SERVICE.learning_summary(), request_id, environ)
        if path == "/api/learning/resources" and method == "GET": return _json_response(start_response, HTTPStatus.OK, {"resources": SERVICE.learning_resources_view(), "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/resources" and method == "POST":
            resource = SERVICE.add_learning_resource(_read_json(environ)); return _json_response(start_response, HTTPStatus.OK, {"resource": {**resource.__dict__, "content_type": resource.content_type.value, "status": resource.status.value}, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/sources" and method == "GET": return _json_response(start_response, HTTPStatus.OK, {"sources": SERVICE.learning_sources_view(), "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/sources/screen" and method == "POST":
            source = SERVICE.screen_learning_source(_read_json(environ)); return _json_response(start_response, HTTPStatus.OK, {"source": source.__dict__, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/sources/validate" and method == "POST":
            data = _read_json(environ)
            source = _learning_source_for_request(str(data.get("source_id", "")))
            result = SERVICE.validate_learning_source(source, content_verified=bool(data.get("content_verified", False)), security_checked=bool(data.get("security_checked", False)))
            return _json_response(start_response, HTTPStatus.OK, {"source": result.__dict__, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/sources/admit" and method == "POST":
            data = _read_json(environ)
            source = _learning_source_for_request(str(data.get("source_id", "")))
            result = SERVICE.admit_learning_knowledge(source, knowledge_validated=bool(data.get("knowledge_validated", False)))
            return _json_response(start_response, HTTPStatus.OK, {"source": result.__dict__, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/observations" and method == "POST":
            result = SERVICE.add_learning_observation(_read_json(environ)); return _json_response(start_response, HTTPStatus.OK, {"observation": result.__dict__, "learning_authorizes_trading": False, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/activities" and method == "POST":
            result = SERVICE.add_learning_activity(_read_json(environ)); return _json_response(start_response, HTTPStatus.OK, {"activity": result.__dict__, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/professor/activity" and method == "POST":
            result = SERVICE.generate_professor_activity(_read_json(environ)); return _json_response(start_response, HTTPStatus.OK, {"activity": result.__dict__, "execution_allowed": False}, request_id, environ)
        if path == "/api/learning/attempts" and method == "POST":
            result = SERVICE.add_learning_attempt(_read_json(environ)); return _json_response(start_response, HTTPStatus.OK, {"attempt": result.__dict__, "execution_allowed": False}, request_id, environ)
        if path == "/manifest.webmanifest" and method == "GET": return _file_response(start_response, WEB_DIR / "manifest.webmanifest", "application/manifest+json", request_id, environ)
        if path == "/" and method == "GET": return _file_response(start_response, WEB_DIR / "index.html", "text/html; charset=utf-8", request_id, environ)
        if path.startswith("/web/") and method == "GET":
            candidate = (ROOT / path.lstrip("/")).resolve()
            if WEB_DIR not in candidate.parents: return _text_response(start_response, HTTPStatus.NOT_FOUND, b"Not Found", request_id, environ)
            if not candidate.is_file(): return _text_response(start_response, HTTPStatus.NOT_FOUND, b"Not Found", request_id, environ)
            content_type = "text/html; charset=utf-8" if candidate.suffix == ".html" else "text/javascript; charset=utf-8" if candidate.suffix == ".js" else "text/css; charset=utf-8" if candidate.suffix == ".css" else "application/octet-stream"
            return _file_response(start_response, candidate, content_type, request_id, environ)
        return _text_response(start_response, HTTPStatus.NOT_FOUND, b"Not Found", request_id, environ)
    except PublicSaaSNotReady as exc: return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": exc.args[0] if exc.args and isinstance(exc.args[0], str) else "Serviço SaaS indisponível", "request_id": request_id}, request_id, environ)
    except PermissionError: return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": "Acesso negado", "request_id": request_id}, request_id, environ)
    except (ValueError, KeyError, TypeError, RuntimeError): return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Entrada inválida", "request_id": request_id}, request_id, environ)
    except Exception: return _json_response(start_response, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Erro interno", "request_id": request_id}, request_id, environ)


def run() -> None:
    host = os.environ.get("CONTROLADOR_HOST", "127.0.0.1")
    port = int(os.environ.get("CONTROLADOR_PORT", "8000"))
    with make_server(host, port, application) as server:
        print(f"Controlador Trading em http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    run()
