from __future__ import annotations

import hmac
import json
import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from core.api_result import serialize_decision_record
from core.ecosystem_onboarding import EcosystemOnboarding
from core.operational_runtime import build_operational_runtime
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.execution_provider import build_demo_execution_port
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter
from core.p122_broker_market_data import BrokerMarketDataBoundary
from integration.persistent_market_data_runtime import MarketDataRuntimeConfig, PersistentMarketDataRuntime
from integration.mt5_asset_suitability_bridge import select_mt5_analysis_candidates
from execution.mt5_instrument_universe import discover_mt5_instruments
from security_guard import MAX_BODY_BYTES, SECURITY
from security_audit import AUDIT

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
RUNTIME_DIR = Path(os.environ.get("CONTROLADOR_RUNTIME_DIR", str(ROOT / ".runtime")))
EXECUTION_PROVIDER = os.environ.get("CONTROLADOR_EXECUTION_PROVIDER", "paper")
EXECUTION_SYMBOL = os.environ.get("CONTROLADOR_EXECUTION_SYMBOL") or None
EXECUTOR = build_demo_execution_port(EXECUTION_PROVIDER, symbol=EXECUTION_SYMBOL)
MARKET_DATA_PROVIDER = os.environ.get("CONTROLADOR_MARKET_DATA_PROVIDER", "ic_markets_mt5_demo").strip().lower()
MARKET_DATA = ICMarketsMT5DemoMarketDataAdapter() if MARKET_DATA_PROVIDER == "ic_markets_mt5_demo" else None
OPERATIONAL_RUNTIME = build_operational_runtime(RUNTIME_DIR, executor=EXECUTOR)
MARKET_DATA_RUNTIME: PersistentMarketDataRuntime | None = None

def _select_mt5_analysis_symbols() -> tuple[str, ...]:
    """Discover the broker universe and return evidence-qualified analysis candidates."""
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError:
        return ()
    if not mt5.initialize():
        return ()
    try:
        statuses = discover_mt5_instruments(mt5)
        candidates = select_mt5_analysis_candidates(
            mt5,
            statuses,
            limit=int(os.environ.get("CONTROLADOR_MARKET_DATA_CANDIDATES", "8")),
        )
        return tuple(candidate.symbol for candidate in candidates)
    finally:
        mt5.shutdown()

if MARKET_DATA is not None:
    MARKET_DATA_RUNTIME = PersistentMarketDataRuntime(
        BrokerMarketDataBoundary(MARKET_DATA, MARKET_DATA_PROVIDER),
        OPERATIONAL_RUNTIME.market_data,
        MarketDataRuntimeConfig(
            symbol=EXECUTION_SYMBOL,
            timeframe=os.environ.get("CONTROLADOR_EXECUTION_TIMEFRAME", "5m"),
            limit=int(os.environ.get("CONTROLADOR_MARKET_DATA_LIMIT", "120")),
            poll_seconds=float(os.environ.get("CONTROLADOR_MARKET_DATA_POLL_SECONDS", "5")),
        ),
        symbol_selector=None,
    )
NOTIFICATION_DB = os.environ.get("CONTROLADOR_NOTIFICATIONS_DB") or str(RUNTIME_DIR / "notifications.sqlite3")
SERVICE = ConfiguredEcosystemService(operational_runtime=OPERATIONAL_RUNTIME, market_data_provider=MARKET_DATA, market_data_source=MARKET_DATA_PROVIDER, notification_database_path=NOTIFICATION_DB, preferences_path=str(RUNTIME_DIR / "preferences.sqlite3"))
ONBOARDING = EcosystemOnboarding()

if MARKET_DATA_RUNTIME is not None:
    candidate_selector = (
        (lambda: (EXECUTION_SYMBOL,))
        if EXECUTION_SYMBOL
        else _select_mt5_analysis_symbols
    )
    MARKET_DATA_RUNTIME.configure_candidate_analysis(
        candidate_selector=candidate_selector,
        candidate_analyzer=SERVICE.evaluate_market_snapshot,
        selected_result_handler=SERVICE.handle_selected_market_analysis,
    )
    MARKET_DATA_RUNTIME.start()


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
            kill_switch_html = (WEB_DIR / "components" / "kill-switch.html").read_text(encoding="utf-8").encode("utf-8")
            kill_switch_js = (WEB_DIR / "components" / "kill-switch.js").read_text(encoding="utf-8")
            notification_html = (WEB_DIR / "components" / "notifications.html").read_text(encoding="utf-8").encode("utf-8")
            notification_js = (WEB_DIR / "components" / "notifications.js").read_text(encoding="utf-8")
            onboarding_html = (WEB_DIR / "components" / "onboarding.html").read_text(encoding="utf-8").encode("utf-8")
            onboarding_js = (WEB_DIR / "components" / "onboarding.js").read_text(encoding="utf-8")
            kill_switch_script = f'<script nonce="{script_nonce}">{kill_switch_js}</script>'.encode("utf-8")
            notification_script = f'<script nonce="{script_nonce}">{notification_js}</script>'.encode("utf-8")
            onboarding_script = f'<script nonce="{script_nonce}">{onboarding_js}</script>'.encode("utf-8")
            kill_switch_mount = kill_switch_html + kill_switch_script
            notification_mount = notification_html + notification_script
            onboarding_mount = onboarding_html + onboarding_script
            anchor = '<div class="section">Visão geral</div>'.encode("utf-8")
            body = body.replace(anchor, notification_mount + onboarding_mount + anchor, 1)
            config_anchor = '<div class="section" id="config">Configurações</div>'.encode("utf-8")
            body = body.replace(config_anchor, kill_switch_mount + config_anchor, 1)
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
        if path == "/api/demo-autonomy" and method == "GET":
            state = OPERATIONAL_RUNTIME.demo_autonomy.state
            return _json_response(start_response, HTTPStatus.OK, {"enabled": state.enabled, "amount": state.amount, "duration_seconds": state.duration_seconds, "max_operations_per_day": state.max_operations_per_day, "authorized_at": state.authorized_at, "authorized_by": state.authorized_by, "mode": "DEMO", "real": False}, request_id, environ)
        if path == "/api/demo-autonomy" and method == "POST":
            authorized, reason = _authorize_internal_update(environ)
            if not authorized:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": reason, "request_id": request_id}, request_id, environ)
            data = _read_json(environ)
            action = str(data.get("action", "")).strip().lower()
            if action == "disable":
                state = OPERATIONAL_RUNTIME.demo_autonomy.disable()
            elif action == "enable":
                state = OPERATIONAL_RUNTIME.demo_autonomy.enable(amount=data.get("amount"), duration_seconds=data.get("duration_seconds"), max_operations_per_day=data.get("max_operations_per_day"), authorized_at=str(data.get("authorized_at", "")), authorized_by=str(data.get("authorized_by", "")))
            else:
                raise ValueError("action deve ser enable ou disable")
            return _json_response(start_response, HTTPStatus.OK, {"enabled": state.enabled, "amount": state.amount, "duration_seconds": state.duration_seconds, "authorized_at": state.authorized_at, "authorized_by": state.authorized_by, "mode": "DEMO", "real": False}, request_id, environ)
        if path == "/api/market/status" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.market_data_status(), request_id, environ)
        if path == "/api/market/analyze" and method == "POST":
            data = _read_json(environ)
            record = SERVICE.analyze_market(symbol=str(data.get("symbol", "")), timeframe=str(data.get("timeframe", "")), limit=int(data.get("limit", 120)))
            return _json_response(start_response, HTTPStatus.OK, {**record.to_dict(), "execution_allowed": False}, request_id, environ)
        if path == "/api/kill-switch" and method == "GET":
            runtime = SERVICE.operational_runtime
            if runtime is None:
                return _json_response(start_response, HTTPStatus.OK, {"enabled": True, "reason": "runtime operacional não conectado", "execution_allowed": False}, request_id, environ)
            state = runtime.kill_switch.state
            return _json_response(start_response, HTTPStatus.OK, {"enabled": state.enabled, "reason": state.reason, "execution_allowed": False}, request_id, environ)
        if path == "/api/kill-switch" and method == "POST":
            data = _read_json(environ)
            runtime = SERVICE.operational_runtime
            if runtime is None:
                raise RuntimeError("runtime operacional não conectado")
            if str(data.get("action", "")).strip().lower() != "activate":
                raise ValueError("somente ativação do Kill switch está disponível pela interface")
            reason = str(data.get("reason", "")).strip()
            if not reason:
                raise ValueError("reason é obrigatório")
            runtime.activate_kill_switch(reason)
            state = runtime.kill_switch.state
            return _json_response(start_response, HTTPStatus.OK, {"enabled": state.enabled, "reason": state.reason, "execution_allowed": False}, request_id, environ)
        if path == "/api/onboarding" and method == "GET":
            guide = ONBOARDING.build_first_use_guide()
            return _json_response(start_response, HTTPStatus.OK, {"guide": {"guide_id": guide.guide_id, "title": guide.title, "steps": [{"step_id": step.step_id, "title": step.title, "purpose": step.purpose, "location": step.location.value, "action_hint": step.action_hint, "technical_details_hidden": step.technical_details_hidden} for step in guide.steps], "completion_message": guide.completion_message, "execution_authorized": guide.execution_authorized}}, request_id, environ)
        if path == "/api/leverage/assess" and method == "POST":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.assess_leverage(_read_json(environ)), request_id, environ)
        if path == "/api/ecosystem-image" and method == "GET":
            kind = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True).get("kind", ["profile"])[-1]
            image = SERVICE.read_ecosystem_image(kind)
            if image is None:
                return _json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "imagem não configurada", "request_id": request_id}, request_id, environ)
            body, content_type = image
            headers = [("Content-Type", content_type), ("Content-Length", str(len(body))), ("Cache-Control", "no-store")]
            headers.extend(SECURITY.headers(request_id))
            start_response("200 OK", headers)
            _audit(environ, request_id, 200)
            return [body]
        if path == "/api/ecosystem-image" and method == "POST":
            kind = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True).get("kind", [""])[-1]
            raw_length = environ.get("CONTENT_LENGTH") or "0"
            length = int(raw_length)
            from core.ecosystem_image_store import EcosystemImageStore
            if length <= 0 or length > EcosystemImageStore.MAX_BYTES:
                raise ValueError("imagem deve ter entre 1 byte e 5 MB")
            payload = environ["wsgi.input"].read(length)
            if len(payload) != length:
                raise ValueError("payload de imagem incompleto")
            mime = SERVICE.save_ecosystem_image(kind, payload, str(environ.get("CONTENT_TYPE", "")))
            return _json_response(start_response, HTTPStatus.OK, {"saved": True, "content_type": mime, "request_id": request_id}, request_id, environ)
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
        if path == "/api/journal" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, SERVICE.daily_journal(_query_limit(environ, 100)), request_id, environ)
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
                decision_id=data.get("decision_id"),
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
        if path == "/icons/icon.svg" and method == "GET":
            return _file_response(start_response, WEB_DIR / "icons" / "icon.svg", "image/svg+xml", request_id, environ)
        if path == "/manifest.webmanifest" and method == "GET":
            return _file_response(start_response, WEB_DIR / "manifest.webmanifest", "application/manifest+json; charset=utf-8", request_id, environ)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Entrada inválida", "request_id": request_id}, request_id, environ)

    headers = [("Content-Type", "text/plain; charset=utf-8")]
    headers.extend(SECURITY.headers(request_id))
    start_response("404 Not Found", headers)
    _audit(environ, request_id, 404)
    return [b"Not Found"]


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    """Allow independent mobile polling/health requests without blocking execution."""

    daemon_threads = True
    allow_reuse_address = True


def run(host: str = "0.0.0.0", port: int | None = None) -> None:
    selected_port = port or int(os.environ.get("PORT", "8000"))
    with make_server(host, selected_port, application, server_class=ThreadedWSGIServer) as server:
        print(f"Controlador Trading em http://{host}:{selected_port}")
        server.serve_forever()


if __name__ == "__main__":
    run()
