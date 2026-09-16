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
from security.http_identity import require_role, require_tenant_scoped_data_plane, require_trusted_identity, saas_public_mode

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
RUNTIME_DIR = Path(os.environ.get("CONTROLADOR_RUNTIME_DIR", str(ROOT / ".runtime")))
EXECUTION_PROVIDER = os.environ.get("CONTROLADOR_EXECUTION_PROVIDER", "paper")
EXECUTION_SYMBOL = os.environ.get("CONTROLADOR_EXECUTION_SYMBOL") or None
EXECUTOR = build_demo_execution_port(EXECUTION_PROVIDER, symbol=EXECUTION_SYMBOL)


def _build_authoritative_risk_provider():
    """Select the broker-edge risk authority without changing core composition."""
    if EXECUTION_PROVIDER != "ic_markets_mt5_demo":
        return None
    raw_timeframe = os.environ.get("CONTROLADOR_EXECUTION_TIMEFRAME", "5").strip()
    try:
        timeframe = int(raw_timeframe)
    except ValueError as exc:
        raise RuntimeError("CONTROLADOR_EXECUTION_TIMEFRAME must be an integer for MT5 DEMO") from exc
    if timeframe <= 0:
        raise RuntimeError("CONTROLADOR_EXECUTION_TIMEFRAME must be greater than zero for MT5 DEMO")
    return MT5DemoRiskStateProvider(
        MT5DemoRiskStateConfig(symbol=EXECUTION_SYMBOL, timeframe=timeframe)
    )


RISK_STATE_PROVIDER = _build_authoritative_risk_provider()
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
    if environ is not None: _audit(environ, request_id, status.value)
    return [body]

def _text_response(start_response, status: HTTPStatus, body: bytes, request_id: str, environ=None) -> list[bytes]:
    headers = [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))] + SECURITY.headers(request_id)
    start_response(f"{status.value} {status.phrase}", headers)
    if environ is not None: _audit(environ, request_id, status.value)
    return [body]

def _read_json(environ) -> dict:
    try: length = int(environ.get("CONTENT_LENGTH") or "0")
    except (TypeError, ValueError) as exc: raise ValueError("Entrada inválida: content-length inválido") from exc
    if length < 0 or length > MAX_BODY_BYTES: raise ValueError("Entrada inválida: payload excede o limite permitido")
    raw = environ["wsgi.input"].read(length)
    if len(raw) > MAX_BODY_BYTES: raise ValueError("Entrada inválida: payload excede o limite permitido")
    try: data = json.loads(raw or b"{}")
    except (TypeError, ValueError) as exc: raise ValueError("Entrada inválida: JSON inválido") from exc
    if not isinstance(data, dict): raise ValueError("Entrada inválida: payload deve ser um objeto JSON")
    return data

def _query_limit(environ, default: int, maximum: int = 100) -> int:
    values = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True).get("limit")
    if not values or values[-1] == "": return default
    try: limit = int(values[-1])
    except (TypeError, ValueError) as exc: raise ValueError("limit deve ser um inteiro") from exc
    if limit < 1: raise ValueError("limit deve ser maior que zero")
    return limit

def _authorize_internal_update(environ) -> tuple[bool, str]:
    expected = os.environ.get("CONTROLADOR_UPDATE_TOKEN", "").strip()
    if not expected: return False, "internal update endpoint is not configured"
    provided = str(environ.get("HTTP_AUTHORIZATION", ""))
    if not provided.startswith("Bearer "): return False, "internal authorization required"
    token = provided[7:].strip()
    if not token or not hmac.compare_digest(token, expected): return False, "internal authorization denied"
    return True, "authorized"

def _authorize_public_saas_request(environ, path: str, method: str) -> None:
    if not saas_public_mode(): return
    if method == "POST" and path in PUBLIC_SAAS_MUTATIONS:
        identity = require_trusted_identity(environ)
        if path in ADMIN_ONLY_SAAS_MUTATIONS: require_role(identity, "admin")
        require_tenant_scoped_data_plane()
    elif method == "GET" and path in PUBLIC_SAAS_READS:
        require_trusted_identity(environ); require_tenant_scoped_data_plane()

def _file_response(start_response, path: Path, content_type: str, request_id: str, environ) -> list[bytes]:
    body = path.read_bytes(); script_nonce = SECURITY.script_nonce() if content_type.startswith("text/html") else None
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
    start_response("200 OK", headers); _audit(environ, request_id, 200); return [body]

def _learning_source_for_request(source_id: str):
    """Resolve a learning source through the scoped service view, never a process-global map."""
    wanted = str(source_id).strip()
    for item in SERVICE.learning_sources_view():
        if str(item.get("source_id", "")) == wanted:
            from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType
            return LearningSource(source_id=wanted, source_type=LearningSourceType(str(item["source_type"]).upper()), uri=str(item["uri"]), status=LearningSourceStatus(str(item["status"]).upper()), content_verified=bool(item.get("content_verified", False)), security_checked=bool(item.get("security_checked", False)), knowledge_validated=bool(item.get("knowledge_validated", False)), operation_eligible=False)
    raise ValueError("source_id não encontrado")

def application(environ, start_response):
    request_id = SECURITY.request_id(); path = environ.get("PATH_INFO", "/"); method = environ.get("REQUEST_METHOD", "GET").upper()
    if not SECURITY.allow(environ): return _json_response(start_response, HTTPStatus.TOO_MANY_REQUESTS, {"error": "Limite de requisições excedido", "request_id": request_id}, request_id, environ)
    try:
        _authorize_public_saas_request(environ, path, method)
        identity = require_trusted_identity(environ) if saas_public_mode() else None
        owner_kwargs = {"subject_id": identity.subject_id, "tenant_id": identity.tenant_id} if identity is not None else {}
        if path == "/api/health" and method == "GET": return _json_response(start_response, HTTPStatus.OK, {"ok": True} if saas_public_mode() else {"ok": True, **SERVICE.system_status()}, request_id, environ)