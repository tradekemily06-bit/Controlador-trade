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
from analysis.decision_store import DecisionStore
from core.operational_runtime import build_operational_runtime
from core.real_runtime_controller import RealRuntimeController
from core.runtime_process_lock import RuntimeProcessLock
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.execution_provider import build_demo_execution_port
from security_guard import MAX_BODY_BYTES, SECURITY
from security_audit import AUDIT

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
RUNTIME_DIR = Path(os.environ.get("CONTROLADOR_RUNTIME_DIR", str(ROOT / ".runtime")))
EXECUTION_PROVIDER = os.environ.get("CONTROLADOR_EXECUTION_PROVIDER", "paper")
EXECUTION_SYMBOL = os.environ.get("CONTROLADOR_EXECUTION_SYMBOL") or None
DECISION_DB = Path(os.environ.get("CONTROLADOR_DECISION_DB", str(RUNTIME_DIR / "decision-memory.sqlite")))
EXECUTOR = build_demo_execution_port(EXECUTION_PROVIDER, symbol=EXECUTION_SYMBOL)
OPERATIONAL_RUNTIME = build_operational_runtime(RUNTIME_DIR, executor=EXECUTOR)
SERVICE = ConfiguredEcosystemService(
    operational_runtime=OPERATIONAL_RUNTIME,
    execution_provider=EXECUTION_PROVIDER,
    decision_store=DecisionStore(str(DECISION_DB)),
)
REAL_RUNTIME = RealRuntimeController(runtime=OPERATIONAL_RUNTIME, root=RUNTIME_DIR, symbol=EXECUTION_SYMBOL)
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


def _authorize_remote_mutation(environ) -> tuple[bool, str]:
    """Authorize remote mutations through the deployment's trusted identity boundary."""
    remote_access_required = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "").strip().lower() in {"1", "true", "yes"}
    identity_header = os.environ.get("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "").strip()
    client = str(environ.get("REMOTE_ADDR") or "").strip()

    if not remote_access_required and (not client or client in {"127.0.0.1", "::1"}):
        return True, "local"

    local_mutations_allowed = os.environ.get("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "").strip().lower() in {"1", "true", "yes"}
    local_hosts = {
        item.strip().lower()
        for item in os.environ.get(
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
            "localhost,127.0.0.1,[::1]",
        ).split(",")
        if item.strip()
    }
    host = str(environ.get("HTTP_HOST") or "").split(":", 1)[0].strip().lower()
    is_loopback = client in {"127.0.0.1", "::1"}
    if local_mutations_allowed and is_loopback and (not host or host in local_hosts):
        return True, "local"

    if not remote_access_required:
        return False, "trusted remote identity provider is not configured"

    if not identity_header:
        return False, "trusted identity header is not configured"

    identity = str(environ.get("HTTP_" + identity_header.upper().replace("-", "_")) or "").strip()
    if not identity:
        return False, "trusted identity is required"

    return True, "trusted"


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

    if method == "POST" and path != "/api/updates":
        raw_length = environ.get("CONTENT_LENGTH")
        try:
            declared_length = int(raw_length) if raw_length not in (None, "") else 0
        except (TypeError, ValueError):
            declared_length = -1
        if declared_length < 0 or declared_length > MAX_BODY_BYTES:
            # Let _read_json return the canonical 400 validation response.
            pass
        else:
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                return _json_response(
                    start_response,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": reason, "request_id": request_id},
                    request_id,
                    environ,
                )

    try:
        if path == "/api/health" and method == "GET":
            status = SERVICE.system_status()
            status["real_runtime"] = REAL_RUNTIME.status()
            return _json_response(start_response, HTTPStatus.OK, {"ok": True, **status}, request_id, environ)
        if path == "/api/status" and method == "GET":
            status = SERVICE.system_status()
            status["real_runtime"] = REAL_RUNTIME.status()
            return _json_response(start_response, HTTPStatus.OK, status, request_id, environ)
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
        if path == "/api/market/candles" and method == "GET":
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            symbol = (query.get("symbol") or ["EURUSD"])[-1].strip() or "EURUSD"
            timeframe = (query.get("timeframe") or ["5m"])[-1].strip() or "5m"
            limit = _query_limit(environ, 80, maximum=200)
            candles = SERVICE.get_mt5_market_candles(symbol=symbol, timeframe=timeframe, limit=limit)
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "source": "IC Markets MT5 DEMO",
                "candles": [
                    {
                        "timestamp": candle.timestamp.isoformat(),
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                    }
                    for candle in candles
                ],
            }
            return _json_response(start_response, HTTPStatus.OK, payload, request_id, environ)
        if path == "/api/runtime/real/status" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK, REAL_RUNTIME.status(), request_id, environ)
        if path == "/api/runtime/real/prepare" and method == "POST":
            data = _read_json(environ)
            prepared = REAL_RUNTIME.prepare(
                request_id=str(data.get("request_id", "")),
                symbol=str(data.get("symbol", "")),
                signal=str(data.get("signal", "")),
                amount=float(data.get("amount", 0)),
                duration_seconds=int(data.get("duration_seconds", 0)),
            )
            return _json_response(start_response, HTTPStatus.OK, {"real_confirmation": prepared}, request_id, environ)
        if path == "/api/runtime/real/confirm" and method == "POST":
            data = _read_json(environ)
            result = REAL_RUNTIME.confirm(
                confirmation_id=str(data.get("confirmation_id", "")),
                request_id=str(data.get("request_id", "")),
                symbol=str(data.get("symbol", "")),
                signal=str(data.get("signal", "")),
                amount=float(data.get("amount", 0)),
                duration_seconds=int(data.get("duration_seconds", 0)),
            )
            execution = result.execution
            return _json_response(start_response, HTTPStatus.OK, {
                "real_execution": {
                    "status": result.status,
                    "message": result.message,
                    "accepted": bool(execution and execution.accepted),
                    "external_id": execution.external_id if execution else None,
                }
            }, request_id, environ)
        if path == "/api/runtime/real/reconcile" and method == "POST":
            data = _read_json(environ)
            REAL_RUNTIME.reconcile(request_id=str(data.get("request_id", "")), executed=bool(data.get("executed", False)))
            return _json_response(start_response, HTTPStatus.OK, {"reconciled": True}, request_id, environ)
        if path == "/api/runtime/real/close" and method == "POST":
            data = _read_json(environ)
            close = REAL_RUNTIME.close_and_reconcile(
                request_id=str(data.get("request_id", "")),
                external_id=str(data.get("external_id", "")),
            )
            return _json_response(start_response, HTTPStatus.OK, {
                "closed": bool(close.accepted),
                "message": close.message,
                "close_external_id": close.external_id,
                "reconciled": bool(close.accepted),
            }, request_id, environ)
        if path == "/api/runtime/close" and method == "POST":
            data = _read_json(environ)
            external_id = str(data.get("external_id", ""))
            cycle_id = str(data.get("cycle_id", ""))
            SERVICE.validate_mt5_cycle_identity(cycle_id=cycle_id, external_id=external_id)
            close_result = SERVICE.close_mt5_position(external_id=external_id)
            reconciliation = None
            if close_result.accepted:
                snapshot = SERVICE.reconcile_mt5_cycle(cycle_id=cycle_id, external_id=external_id)
                reconciliation = None if snapshot is None else {
                    "cycle_id": snapshot.cycle_id,
                    "terminal_state": snapshot.terminal_state,
                    "reconciliation_state": snapshot.reconciliation_state.value,
                }
            return _json_response(start_response, HTTPStatus.OK, {
                "closed": close_result.accepted,
                "message": close_result.message,
                "close_external_id": close_result.external_id,
                "reconciliation": reconciliation,
            }, request_id, environ)
        if path == "/api/runtime/reconcile" and method == "POST":
            data = _read_json(environ)
            snapshot = SERVICE.reconcile_mt5_cycle(
                cycle_id=str(data.get("cycle_id", "")),
                external_id=str(data.get("external_id", "")),
            )
            payload = None if snapshot is None else {
                "cycle_id": snapshot.cycle_id,
                "terminal_state": snapshot.terminal_state,
                "outcome": snapshot.outcome,
                "financial_result": snapshot.financial_result,
                "reconciliation_state": snapshot.reconciliation_state.value,
            }
            return _json_response(start_response, HTTPStatus.OK, {"runtime_reconciliation": payload}, request_id, environ)
        if path == "/api/runtime/cycle" and method == "POST":
            data = _read_json(environ)
            result = SERVICE.run_mt5_cycle(
                symbol=str(data.get("symbol", "")),
                timeframe=str(data.get("timeframe", "5m")),
                limit=int(data.get("limit", 100)),
                amount=float(data.get("amount", 0.01)),
                duration_seconds=int(data.get("duration_seconds", 60)),
                confirmed=bool(data.get("confirmed", False)),
                filters_ok=bool(data.get("filters_ok", True)),
                entry_conditions=tuple(data.get("entry_conditions", ()) or ()),
            )
            cycle = result.cycles[-1]
            execution = cycle.execution
            payload = {
                "stopped": result.stopped,
                "stop_reason": result.stop_reason,
                "decision": cycle.orchestration.decision.decision,
                "signal": cycle.orchestration.analysis.signal.value,
                "score": cycle.orchestration.analysis.score,
                "reason": cycle.orchestration.decision.reason,
                "market_context": cycle.orchestration.snapshot.market_context.context.value if cycle.orchestration.snapshot.market_context else None,
                "market_data_source": cycle.orchestration.market_data.source,
                "candles": len(cycle.orchestration.market_data.candles),
                "request_id": cycle.plan.request_id if cycle.plan else None,
                "cycle_id": (
                    cycle.orchestration.senior_context.cycle_id
                    if cycle.orchestration.senior_context is not None
                    else (cycle.automation_lifecycle.cycle_id if cycle.automation_lifecycle is not None else None)
                ),
                "execution": {"accepted": execution.accepted, "status": execution.status.value, "message": execution.message, "external_id": execution.external_id} if execution else None,
            }
            return _json_response(start_response, HTTPStatus.OK, {"runtime": payload, "execution_allowed": bool(execution and execution.accepted)}, request_id, environ)
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
    except PermissionError as exc:
        return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "request_id": request_id}, request_id, environ)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Entrada inválida", "request_id": request_id}, request_id, environ)

    headers = [("Content-Type", "text/plain; charset=utf-8")]
    headers.extend(SECURITY.headers(request_id))
    start_response("404 Not Found", headers)
    _audit(environ, request_id, 404)
    return [b"Not Found"]


def run(host: str | None = None, port: int | None = None) -> None:
    selected_host = host or os.environ.get("CONTROLADOR_BIND_HOST", "127.0.0.1")
    selected_port = port or int(os.environ.get("PORT", "8000"))
    lock = RuntimeProcessLock(RUNTIME_DIR / "controlador-runtime.lock")
    with lock:
        with make_server(selected_host, selected_port, application) as server:
            print(f"Controlador Trading em http://{selected_host}:{selected_port}")
            server.serve_forever()


if __name__ == "__main__":
    run()
