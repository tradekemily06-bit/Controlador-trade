from __future__ import annotations

import hmac
import json
import math
import os
import sqlite3
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo
from socketserver import ThreadingMixIn
from threading import Lock
from wsgiref.simple_server import WSGIServer, make_server

from core.api_result import serialize_decision_record
from core.ecosystem_onboarding import EcosystemOnboarding
from analysis.decision_store import DecisionStore
from core.operational_runtime import build_operational_runtime
from core.real_runtime_controller import RealRuntimeController
from core.runtime_process_lock import RuntimeProcessLockSet
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from core.ecosystem_state_store import NotificationHistoryUnavailableError
from core.latest_market_analysis_store import LatestMarketAnalysisStore
from integration.execution_provider import build_demo_execution_port
from security_guard import MAX_BODY_BYTES, SECURITY
from security_audit import AUDIT
from finance.fiscal_reserve import FiscalReserve, MAX_FISCAL_HISTORY_OFFSET
from finance.fiscal_taxonomy import fiscal_classification_catalog
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_schema import migrate_fiscal_schema
from finance.fiscal_identity import FiscalOwnerIdentityError, configured_fiscal_owner_id
from assistant.conversation_store import AssistantConversationStore
from assistant.chat_service import EcosystemAssistant, AssistantUnavailableError
from execution.icmarkets_mt5_demo_adapter import MT5DealNotFoundError

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
RUNTIME_DIR = Path(os.environ.get("CONTROLADOR_RUNTIME_DIR", str(ROOT / ".runtime"))).expanduser().resolve()
EXECUTION_PROVIDER = os.environ.get("CONTROLADOR_EXECUTION_PROVIDER", "paper")
EXECUTION_SYMBOL = os.environ.get("CONTROLADOR_EXECUTION_SYMBOL") or None
DECISION_DB = Path(os.environ.get("CONTROLADOR_DECISION_DB", str(RUNTIME_DIR / "decision-memory.sqlite"))).expanduser().resolve()
FISCAL_RESERVE_DB = Path(os.environ.get("CONTROLADOR_FISCAL_RESERVE_DB", str(RUNTIME_DIR / "fiscal-reserve.sqlite3"))).expanduser().resolve()
ASSISTANT_DB = Path(os.environ.get("CONTROLADOR_ASSISTANT_DB", str(RUNTIME_DIR / "assistant.sqlite3"))).expanduser().resolve()
ANALYSIS_SNAPSHOT_DB = Path(os.environ.get("CONTROLADOR_ANALYSIS_SNAPSHOT_DB", str(RUNTIME_DIR / "latest-market-analysis.sqlite3"))).expanduser().resolve()
# Lock the runtime directory and every configured SQLite database before any
# runtime service, repository, or fiscal migration can touch shared state.
_RUNTIME_PROCESS_LOCK = RuntimeProcessLockSet(
    RUNTIME_DIR / "controlador-runtime.lock",
    [DECISION_DB, FISCAL_RESERVE_DB, ASSISTANT_DB, ANALYSIS_SNAPSHOT_DB],
)
try:
    _RUNTIME_PROCESS_LOCK.acquire()
    EXECUTOR = build_demo_execution_port(EXECUTION_PROVIDER, symbol=EXECUTION_SYMBOL)
    OPERATIONAL_RUNTIME = build_operational_runtime(RUNTIME_DIR, executor=EXECUTOR)
    SERVICE = ConfiguredEcosystemService(
        operational_runtime=OPERATIONAL_RUNTIME,
        execution_provider=EXECUTION_PROVIDER,
        decision_store=DecisionStore(str(DECISION_DB)),
    )
    REAL_RUNTIME = RealRuntimeController(runtime=OPERATIONAL_RUNTIME, root=RUNTIME_DIR, symbol=EXECUTION_SYMBOL)
    ONBOARDING = EcosystemOnboarding()
    # Apply the owner-scoped schema before any fiscal repository creates or queries tables.
    # This fails closed when the configured single-owner identity is absent or mismatched.
    migrate_fiscal_schema(str(FISCAL_RESERVE_DB))
    FISCAL_RESERVE = FiscalReserve(str(FISCAL_RESERVE_DB))
    FISCAL_PENDING_QUEUE = FiscalPendingQueue(str(FISCAL_RESERVE_DB))
    FISCAL_DOMESTIC_PENDING_QUEUE = FiscalDomesticPendingQueue(str(FISCAL_RESERVE_DB))
    ASSISTANT_STORE = AssistantConversationStore(ASSISTANT_DB)
    LATEST_MARKET_ANALYSIS = LatestMarketAnalysisStore(ANALYSIS_SNAPSHOT_DB)
    ASSISTANT = EcosystemAssistant(ASSISTANT_STORE, SERVICE, FISCAL_RESERVE, fiscal_pending_queue=FISCAL_PENDING_QUEUE, fiscal_domestic_pending_queue=FISCAL_DOMESTIC_PENDING_QUEUE)
except BaseException:
    # Import-time startup can fail under a WSGI supervisor that keeps its
    # process alive. Release every acquired sidecar lock before propagating
    # the original initialization failure; never leave a half-built runtime
    # holding shared SQLite/runtime locks indefinitely.
    try:
        _RUNTIME_PROCESS_LOCK.release()
    except Exception:
        # Preserve the initialization exception as the primary failure.
        pass
    raise

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


def _mode_execution_block_reason(preferences: dict) -> str:
    selected_mode = str(preferences.get("selected_mode", "DEMO")).upper()
    if selected_mode == "REAL":
        return "Modo REAL selecionado; execução REAL permanece bloqueada até validação e autorização explícita."
    if preferences.get("leverage_enabled") is True:
        return "Modo de alavancagem selecionado; execução bloqueada até perfil e orçamento de risco validados."
    return ""


def _blocked_cycle_payload(orchestration, reason: str) -> dict:
    candidate_signal = orchestration.analysis.signal.value
    return {
        "stopped": True,
        "stop_reason": reason,
        "analysis_cycle": {
            "timestamp": orchestration.timestamp.isoformat(),
            "symbol": orchestration.analysis.symbol,
            "timeframe": orchestration.analysis.timeframe,
        },
        "decision": "AGUARDAR",
        "signal": "AGUARDAR",
        "candidate_signal": candidate_signal,
        "score": orchestration.analysis.score,
        "reason": reason,
        "analysis": {
            "signal": "AGUARDAR",
            "candidate_signal": candidate_signal,
            "score": orchestration.analysis.score,
            "reason": orchestration.analysis.reason,
            "confirmed": orchestration.analysis.confirmed,
            "symbol": orchestration.analysis.symbol,
            "timeframe": orchestration.analysis.timeframe,
        },
        "quality": {
            "score": orchestration.quality.score,
            "level": orchestration.quality.level.value,
            "actionable": False,
        },
        "market_context": orchestration.snapshot.market_context.context.value if orchestration.snapshot.market_context else None,
        "market_data_source": orchestration.market_data.source,
        "candles": len(orchestration.market_data.candles),
        "request_id": None,
        "cycle_id": None,
        "external_id": None,
        "execution_status": "BLOCKED",
        "execution": {"accepted": False, "status": "BLOCKED", "message": reason, "external_id": None},
    }


def _authorize_remote_mutation(environ) -> tuple[bool, str]:
    """Authorize remote mutations through the deployment's trusted identity boundary."""
    remote_access_required = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "").strip().lower() in {"1", "true", "yes"}
    identity_header = os.environ.get("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "").strip()
    client = str(environ.get("REMOTE_ADDR") or "").strip()
    is_loopback = client in {"127.0.0.1", "::1"}

    if not remote_access_required and is_loopback:
        local_mutations_allowed = os.environ.get("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "").strip().lower() in {"1", "true", "yes"}
        if not local_mutations_allowed:
            return False, "local mutations are disabled"
        local_hosts = {
            item.strip().lower()
            for item in os.environ.get(
                "CONTROLADOR_LOCAL_MUTATION_HOSTS",
                "localhost,127.0.0.1,[::1]",
            ).split(",")
            if item.strip()
        }
        raw_host = str(environ.get("HTTP_HOST") or "").strip().lower()
        if raw_host.startswith("[") and "]" in raw_host:
            host = raw_host[1:raw_host.index("]")]
        else:
            host = raw_host.split(":", 1)[0]
        if host and host not in local_hosts and f"[{host}]" not in local_hosts:
            return False, "local host is not allowed"
        return True, "local"

    if not remote_access_required:
        return False, "trusted remote identity provider is not configured"

    if not identity_header:
        return False, "trusted identity header is not configured"

    identity_value = environ.get("HTTP_" + identity_header.upper().replace("-", "_"))
    if not isinstance(identity_value, str) or not identity_value.strip():
        return False, "trusted identity is required"
    identity = identity_value.strip()
    # Enforce the same bounded, control-character-free identity contract at
    # the API boundary; the API must not rely solely on Streamlit validation.
    if len(identity) > 320 or any(ord(character) < 32 or ord(character) == 127 for character in identity):
        return False, "trusted identity is invalid"

    # Optional single-user pin: when configured, every remote fiscal/assistant
    # request must resolve to this exact normalized Access identity.
    expected_identity = os.environ.get("CONTROLADOR_SINGLE_USER_IDENTITY", "").strip()
    if not expected_identity:
        return False, "single-user identity is not configured"
    if len(expected_identity) > 320 or any(
        ord(character) < 32 or ord(character) == 127
        for character in expected_identity
    ):
        return False, "single-user identity configuration is invalid"
    if identity.casefold() != expected_identity.casefold():
        return False, "authenticated identity is not authorized for this single-user runtime"

    return True, "trusted"


def _remote_identity_http_status(reason: str) -> HTTPStatus:
    """Map authentication failures consistently without hiding deployment errors."""
    if reason in {"trusted identity is required", "trusted identity is invalid"}:
        return HTTPStatus.UNAUTHORIZED
    if reason in {
        "trusted identity header is not configured",
        "single-user identity is not configured",
        "single-user identity configuration is invalid",
        "trusted remote identity provider is not configured",
    }:
        return HTTPStatus.SERVICE_UNAVAILABLE
    return HTTPStatus.FORBIDDEN



def _authorize_local_runtime(environ) -> tuple[bool, str]:
    """Authorize native terminal calls only from a loopback client using an allowed local Host."""
    client = str(environ.get("REMOTE_ADDR") or "").strip()
    if client not in {"127.0.0.1", "::1"}:
        return False, "local runtime requires loopback"
    # A reverse proxy/tunnel may itself connect from loopback. If the request
    # carries the configured trusted Access identity, it is a proxied remote
    # request and must not use the native-terminal exception.
    identity_header = os.environ.get("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "").strip()
    if identity_header:
        identity_key = "HTTP_" + identity_header.upper().replace("-", "_")
        if str(environ.get(identity_key) or "").strip():
            return False, "trusted remote identity cannot use local runtime routes"
    enabled = os.environ.get("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return False, "local mutations are disabled"
    allowed_hosts = {
        item.strip().lower()
        for item in os.environ.get("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
        if item.strip()
    }
    raw_host = str(environ.get("HTTP_HOST") or "").strip().lower()
    if raw_host.startswith("[") and "]" in raw_host:
        host = raw_host[1:raw_host.index("]")]
    else:
        host = raw_host.split(":", 1)[0]
    if not host or host not in allowed_hosts and f"[{host}]" not in allowed_hosts:
        return False, "local Host is not allowed"
    return True, "local"

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
    # O supervisor local precisa consultar o health com frequência. Esse probe é
    # somente leitura e só pode ser isento do rate limit quando vem do loopback.
    # O limite continua valendo para health remoto e para toda a API restante.
    is_local_health_probe = (
        method == "GET"
        and path in {"/api/health", "/api/health/live"}
        and str(environ.get("REMOTE_ADDR") or "") in {"127.0.0.1", "::1"}
    )
    if not is_local_health_probe and not SECURITY.allow(environ):
        return _json_response(start_response, HTTPStatus.TOO_MANY_REQUESTS, {"error": "Limite de requisições excedido", "request_id": request_id}, request_id, environ)

    # Native EA aliases have a dedicated loopback/Host gate. Keep the
    # exception allowlist exact: no generic local POST bypass is permitted.
    local_ea_route_aliases = {
        "/api/runtime/analysis/local": "/api/runtime/analysis",
        "/api/runtime/cycle/local": "/api/runtime/cycle",
        "/api/preferences/local": "/api/preferences",
    }
    local_ea_post_paths = {
        "/api/runtime/close/local/reconcile",
        "/api/runtime/close/local",
        *local_ea_route_aliases.keys(),
    }
    if method == "POST" and path in local_ea_route_aliases:
        authorized, reason = _authorize_local_runtime(environ)
        if not authorized:
            return _json_response(
                start_response,
                HTTPStatus.FORBIDDEN,
                {"error": reason, "execution_allowed": False},
                request_id,
                environ,
            )
    if method == "POST" and path != "/api/updates" and path not in local_ea_post_paths and not path.startswith("/api/assistant/"):
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
                status = _remote_identity_http_status(reason)
                return _json_response(
                    start_response,
                    status,
                    {"error": reason, "request_id": request_id},
                    request_id,
                    environ,
                )

    # Route aliases are normalized only after their dedicated local gate passed.
    # The canonical handlers remain the single source of business logic.
    if method == "POST" and path in local_ea_route_aliases:
        path = local_ea_route_aliases[path]

    try:
        if path == "/api/health/live" and method == "GET":
            # Liveness only: do not query broker, database, risk or observability.
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {"ok": True, "live": True, "service": "controlador"},
                request_id,
                environ,
            )
        if path == "/api/runtime/kill-switch/activate" and method == "POST":
            data = _read_json(environ)
            confirmed = data.get("confirmed")
            reason = data.get("reason")
            if confirmed is not True:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": "confirmação explícita obrigatória", "execution_allowed": False},
                    request_id, environ,
                )
            if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 240:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": "informe um motivo de até 240 caracteres", "execution_allowed": False},
                    request_id, environ,
                )
            state = OPERATIONAL_RUNTIME.operational_recorder.activate_kill_switch(reason.strip())
            observability = SERVICE.operational_observability()
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "activated": state.enabled,
                    "kill_switch": observability["kill_switch"],
                    "execution_allowed": False,
                    "pending_request_ids": observability["reconciliation"]["pending_request_ids"],
                    "unknown_request_ids": observability["reconciliation"]["unknown_request_ids"],
                    "message": "Novas execuções bloqueadas. Solicitações já encaminhadas não são canceladas; reconcilie seus estados.",
                },
                request_id, environ,
            )
        if path == "/api/health" and method == "GET":
            status = SERVICE.system_status()
            status["real_runtime"] = REAL_RUNTIME.status()
            return _json_response(start_response, HTTPStatus.OK, {"ok": True, **status}, request_id, environ)
        if path == "/api/status" and method == "GET":
            status = SERVICE.system_status()
            status["real_runtime"] = REAL_RUNTIME.status()
            return _json_response(start_response, HTTPStatus.OK, status, request_id, environ)
        if path == "/api/security/audit" and method == "GET":
            remote_required = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "").strip().lower() in {"1", "true", "yes"}
            client = str(environ.get("REMOTE_ADDR") or "").strip()
            if remote_required:
                authorized, reason = _authorize_remote_mutation(environ)
                if not authorized:
                    auth_status = _remote_identity_http_status(reason)
                    return _json_response(start_response, auth_status, {"error": "Identidade autenticada necessária para consultar a auditoria."}, request_id, environ)
            elif client not in {"127.0.0.1", "::1"}:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": "Auditoria disponível somente em acesso local ou remoto autenticado."}, request_id, environ)
            limit = _query_limit(environ, 50, maximum=200)
            snapshot = AUDIT.snapshot()
            events = [
                {
                    "timestamp": event.get("timestamp"),
                    "request_id": event.get("request_id"),
                    "method": event.get("method"),
                    "path": event.get("path"),
                    "status": event.get("status"),
                }
                for event in reversed(snapshot[-limit:])
            ]
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {"events": events, "count": len(snapshot), "returned": len(events),
                 "retention_limit": AUDIT.max_events,
                 "persistence": (
                     "NOT_CONFIGURED"
                     if not AUDIT.persistence_available and AUDIT.persistence_error is None
                     else "DURABLE"
                     if AUDIT.persistence_available
                     else str(AUDIT.persistence_error or "unavailable").upper()
                 ),
                 "execution_allowed": False},
                request_id,
                environ,
            )
        if path in {"/api/assistant/local/status", "/api/assistant/local/chat"}:
            authorized, reason = _authorize_local_runtime(environ)
            if not authorized:
                return _json_response(
                    start_response, _remote_identity_http_status(reason),
                    {"error": "Acesso local do terminal não autorizado."}, request_id, environ
                )
            try:
                local_owner_id = configured_fiscal_owner_id()
            except FiscalOwnerIdentityError:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "Identidade proprietária indisponível para o Assistente do Ecossistema."},
                    request_id, environ
                )
            if path == "/api/assistant/local/status" and method == "GET":
                return _json_response(
                    start_response, HTTPStatus.OK, ASSISTANT.readiness(), request_id, environ
                )
            if path == "/api/assistant/local/chat" and method == "POST":
                chat_data = _read_json(environ)
                if chat_data.get("consent_to_openai") is not True:
                    return _json_response(
                        start_response, HTTPStatus.BAD_REQUEST,
                        {"error": "Consentimento explícito para envio do contexto à OpenAI é obrigatório."},
                        request_id, environ
                    )
                try:
                    migrate_fiscal_schema(str(FISCAL_RESERVE_DB))
                except (FiscalOwnerIdentityError, RuntimeError):
                    return _json_response(
                        start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "Reserva Fiscal indisponível até validar a identidade proprietária e a migração."},
                        request_id, environ
                    )
                try:
                    result = ASSISTANT.ask(
                        local_owner_id, chat_data.get("message"), local_owner_id,
                        chat_data.get("conversation_id")
                    )
                except AssistantUnavailableError as exc:
                    return _json_response(
                        start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "Assistente temporariamente indisponível; consulte o histórico antes de reenviar.",
                         "conversation_id": exc.conversation_id},
                        request_id, environ
                    )
                return _json_response(start_response, HTTPStatus.OK, result, request_id, environ)
            return _json_response(
                start_response, HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "Método não permitido."}, request_id, environ
            )
        if path.startswith("/api/assistant/"):
            authorized, auth_reason = _authorize_remote_mutation(environ)
            if not authorized:
                auth_status = _remote_identity_http_status(auth_reason)
                public_reason = (
                    "Identidade autenticada necessária."
                    if auth_reason == "trusted identity is required"
                    else "Identidade autenticada não autorizada para este runtime."
                    if "not authorized for this single-user runtime" in auth_reason
                    else auth_reason
                )
                return _json_response(start_response, auth_status, {"error": public_reason}, request_id, environ)
            assistant_chat_data = None
            if path == "/api/assistant/chat" and method == "POST":
                assistant_chat_data = _read_json(environ)
                if assistant_chat_data.get("consent_to_openai") is not True:
                    return _json_response(
                        start_response,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Consentimento explícito para envio do contexto à OpenAI é obrigatório."},
                        request_id,
                        environ,
                    )
            try:
                # Conversation ownership comes from trusted server configuration;
                # listing/history/deletion must not migrate or touch the fiscal DB.
                identity = configured_fiscal_owner_id()
            except FiscalOwnerIdentityError:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                      {"error": "Identidade proprietária indisponível para o Assistente do Ecossistema."}, request_id, environ)
            if path == "/api/assistant/chat" and method == "POST":
                try:
                    # A fiscal schema migration is required only when assembling
                    # fiscal context for an explicitly consented OpenAI request.
                    migrate_fiscal_schema(str(FISCAL_RESERVE_DB))
                except (FiscalOwnerIdentityError, RuntimeError):
                    return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                          {"error": "Reserva Fiscal indisponível até validar a identidade proprietária e a migração."}, request_id, environ)
            fiscal_owner_id = identity
            if path == "/api/assistant/status" and method == "GET":
                return _json_response(start_response, HTTPStatus.OK, ASSISTANT.readiness(), request_id, environ)
            if path == "/api/assistant/test-connection" and method == "POST":
                try:
                    test_result = ASSISTANT.test_connection()
                except AssistantUnavailableError as exc:
                    return _json_response(
                        start_response,
                        HTTPStatus.BAD_GATEWAY,
                        {"success": False, "connection_tested": False, "status": "CONNECTION_TEST_FAILED",
                         "message": str(exc), "context_sent": False, "history_sent": False,
                         "conversation_saved": False},
                        request_id,
                        environ,
                    )
                return _json_response(start_response, HTTPStatus.OK, test_result, request_id, environ)
            if path == "/api/assistant/conversations" and method == "GET":
                return _json_response(start_response, HTTPStatus.OK, {"conversations": ASSISTANT.conversations(identity)}, request_id, environ)
            if path == "/api/assistant/conversations" and method == "DELETE":
                query = parse_qs(environ.get("QUERY_STRING") or "").get("conversation_id", [""])[-1]
                if not query:
                    raise ValueError("conversation_id obrigatório")
                try:
                    ASSISTANT.delete_conversation(identity, query)
                except PermissionError:
                    return _json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "conversa não encontrada"}, request_id, environ)
                return _json_response(start_response, HTTPStatus.OK, {"deleted": True}, request_id, environ)
            if path == "/api/assistant/history" and method == "GET":
                query = parse_qs(environ.get("QUERY_STRING") or "").get("conversation_id", [""])[-1]
                if not query: raise ValueError("conversation_id obrigatório")
                try:
                    messages = ASSISTANT.history(identity, query)
                except PermissionError:
                    return _json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "conversa não encontrada"}, request_id, environ)
                return _json_response(start_response, HTTPStatus.OK, {"messages": messages}, request_id, environ)
            if path == "/api/assistant/chat" and method == "POST":
                return _json_response(start_response, HTTPStatus.OK, ASSISTANT.ask(identity, assistant_chat_data.get("message"), fiscal_owner_id, assistant_chat_data.get("conversation_id")), request_id, environ)
        if path == "/api/fiscal-reserve/local" and method == "GET":
            authorized, reason = _authorize_local_runtime(environ)
            if not authorized:
                return _json_response(
                    start_response, _remote_identity_http_status(reason),
                    {"error": "Acesso local do terminal não autorizado."}, request_id, environ
                )
            try:
                local_fiscal_owner_id = migrate_fiscal_schema(str(FISCAL_RESERVE_DB))
            except (FiscalOwnerIdentityError, RuntimeError):
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "Reserva Fiscal indisponível até validar a identidade proprietária e a migração."},
                    request_id, environ
                )
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            try:
                history_limit = int(query.get("limit", ["20"])[-1] or "20")
                history_offset = int(query.get("offset", ["0"])[-1] or "0")
            except (TypeError, ValueError) as exc:
                raise ValueError("limit e offset devem ser inteiros") from exc
            if not 1 <= history_limit <= 100 or not 0 <= history_offset <= MAX_FISCAL_HISTORY_OFFSET:
                raise ValueError("paginação fiscal local inválida")
            fiscal_summary = FISCAL_RESERVE.summary(
                local_fiscal_owner_id, history_limit=history_limit, history_offset=history_offset
            )
            fiscal_summary["classification_catalog"] = fiscal_classification_catalog()
            try:
                fiscal_summary["foreign_pending"] = FISCAL_PENDING_QUEUE.summary(local_fiscal_owner_id)
            except (sqlite3.Error, RuntimeError, ValueError):
                fiscal_summary["foreign_pending"] = {
                    "available": False, "classification_status": "PENDING_CLASSIFICATION",
                    "included_in_totals": False, "reserve_calculated": False,
                }
            try:
                fiscal_summary["domestic_pending"] = FISCAL_DOMESTIC_PENDING_QUEUE.summary(local_fiscal_owner_id)
            except (sqlite3.Error, RuntimeError, ValueError):
                fiscal_summary["domestic_pending"] = {
                    "available": False, "classification_status": "PENDING_CLASSIFICATION",
                    "included_in_totals": False, "reserve_calculated": False,
                }
            foreign = fiscal_summary.get("categories", {}).get("FOREIGN_FINANCIAL_ASSET")
            if isinstance(foreign, dict):
                foreign.pop("rate", None)
                foreign["realized_result_brl"] = 0.0
                foreign["reserve_amount_brl"] = 0.0
                foreign["classification_status"] = "PENDING_CLASSIFICATION"
                foreign["rate_available"] = False
            for entry in fiscal_summary.get("history", []):
                if isinstance(entry, dict) and entry.get("category") == "FOREIGN_FINANCIAL_ASSET":
                    entry.pop("reserve_rate", None)
                    entry.pop("reserve_amount_brl", None)
                    entry["classification_status"] = "PENDING_CLASSIFICATION"
            return _json_response(start_response, HTTPStatus.OK, fiscal_summary, request_id, environ)
        if path.startswith("/api/fiscal-reserve"):
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                return _json_response(start_response, _remote_identity_http_status(reason), {"error": reason, "request_id": request_id}, request_id, environ)
            try:
                fiscal_owner_id = migrate_fiscal_schema(str(FISCAL_RESERVE_DB))
            except (FiscalOwnerIdentityError, RuntimeError) as exc:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                      {"error": "Reserva Fiscal indisponível até validar a identidade proprietária e a migração."}, request_id, environ)
        if path == "/api/fiscal-reserve/domestic-pending" and method == "GET":
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            try:
                limit = int(query.get("limit", ["100"])[-1] or "100")
                offset = int(query.get("offset", ["0"])[-1] or "0")
            except (TypeError, ValueError) as exc:
                raise ValueError("limit e offset devem ser inteiros") from exc
            return _json_response(start_response, HTTPStatus.OK,
                                  FISCAL_DOMESTIC_PENDING_QUEUE.list_pending(fiscal_owner_id, limit, offset),
                                  request_id, environ)
        if path == "/api/fiscal-reserve/domestic-pending/summary" and method == "GET":
            return _json_response(start_response, HTTPStatus.OK,
                                  FISCAL_DOMESTIC_PENDING_QUEUE.summary(fiscal_owner_id),
                                  request_id, environ)
        if path == "/api/fiscal-reserve/domestic-pending" and method == "POST":
            try:
                item = FISCAL_DOMESTIC_PENDING_QUEUE.add(fiscal_owner_id, _read_json(environ))
            except sqlite3.IntegrityError:
                return _json_response(start_response, HTTPStatus.CONFLICT,
                                      {"error": "Já existe uma pendência brasileira com essa referência."},
                                      request_id, environ)
            return _json_response(start_response, HTTPStatus.CREATED,
                                  {"pending": item, "reserve_calculated": False,
                                   "classification_status": "PENDING_CLASSIFICATION"},
                                  request_id, environ)
        if path.startswith("/api/fiscal-reserve/domestic-pending/") and path.endswith("/reviews"):
            pending_id = path[len("/api/fiscal-reserve/domestic-pending/"):-len("/reviews")].strip("/")
            if not pending_id or "/" in pending_id:
                raise ValueError("pending_id inválido")
            if method == "GET":
                try:
                    reviews = FISCAL_DOMESTIC_PENDING_QUEUE.list_reviews(fiscal_owner_id, pending_id)
                except ValueError:
                    # Missing and foreign-owned identifiers have the same public read result.
                    reviews = []
                return _json_response(start_response, HTTPStatus.OK,
                                      {"reviews": reviews,
                                       "status_unchanged": "PENDING_CLASSIFICATION",
                                       "reserve_calculated": False},
                                      request_id, environ)
            if method == "POST":
                review = FISCAL_DOMESTIC_PENDING_QUEUE.record_review(
                    fiscal_owner_id, pending_id, _read_json(environ)
                )
                return _json_response(start_response, HTTPStatus.CREATED,
                                      {"review": review, "reserve_calculated": False},
                                      request_id, environ)
        if path == "/api/fiscal-reserve/pending" and method == "GET":
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            try:
                limit = int(query.get("limit", ["100"])[-1] or "100")
                offset = int(query.get("offset", ["0"])[-1] or "0")
            except (TypeError, ValueError) as exc:
                raise ValueError("limit e offset devem ser inteiros") from exc
            return _json_response(start_response, HTTPStatus.OK,
                                  FISCAL_PENDING_QUEUE.list_pending(fiscal_owner_id, limit=limit, offset=offset),
                                  request_id, environ)
        if path == "/api/fiscal-reserve/pending" and method == "POST":
            try:
                item = FISCAL_PENDING_QUEUE.add(fiscal_owner_id, _read_json(environ))
            except sqlite3.IntegrityError:
                return _json_response(start_response, HTTPStatus.CONFLICT,
                                      {"error": "Já existe uma pendência com essa referência.", "request_id": request_id},
                                      request_id, environ)
            return _json_response(start_response, HTTPStatus.CREATED,
                                  {"pending": item, "reserve_calculated": False},
                                  request_id, environ)
        if path == "/api/fiscal-reserve/pending-result" and method == "POST":
            try:
                item = FISCAL_PENDING_QUEUE.add_realized_result(fiscal_owner_id, _read_json(environ))
            except sqlite3.IntegrityError:
                return _json_response(start_response, HTTPStatus.CONFLICT,
                                      {"error": "Já existe uma pendência com essa referência."},
                                      request_id, environ)
            return _json_response(start_response, HTTPStatus.CREATED,
                                  {"pending": item, "reserve_calculated": False,
                                   "classification_status": "PENDING_CLASSIFICATION"},
                                  request_id, environ)
        if path.startswith("/api/fiscal-reserve/pending/") and path.endswith("/reviews"):
            pending_id = path[len("/api/fiscal-reserve/pending/"):-len("/reviews")].strip("/")
            if not pending_id or "/" in pending_id:
                raise ValueError("pending_id inválido")
            if method == "GET":
                try:
                    reviews = FISCAL_PENDING_QUEUE.list_reviews(fiscal_owner_id, pending_id)
                except ValueError:
                    # Missing and foreign-owned identifiers have the same public read result.
                    reviews = []
                return _json_response(start_response, HTTPStatus.OK,
                                      {"reviews": reviews,
                                       "status_unchanged": "PENDING_CLASSIFICATION",
                                       "reserve_calculated": False},
                                      request_id, environ)
            if method == "POST":
                review = FISCAL_PENDING_QUEUE.record_review(fiscal_owner_id, pending_id, _read_json(environ))
                return _json_response(start_response, HTTPStatus.CREATED,
                                      {"review": review, "reserve_calculated": False},
                                      request_id, environ)
        if path == "/api/fiscal-reserve/mt5-pending-result" and method == "POST":
            data = _read_json(environ)
            if data.get("confirmed") is not True:
                raise ValueError("confirmação explícita obrigatória para guardar como pendente")
            ticket = str(data.get("ticket") or "").strip()
            if not ticket or len(ticket) > 80:
                raise ValueError("ticket MT5 é obrigatório e deve ter até 80 caracteres")
            with getattr(SERVICE.mt5_operational_adapter, "session_lock", nullcontext()):
                try:
                    candidate = SERVICE.mt5_operational_adapter.read_closed_deal_candidate(ticket)
                except MT5DealNotFoundError:
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Ticket não encontrado como encerramento integral e conciliado no histórico MT5 DEMO.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                except RuntimeError as exc:
                    return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                          {"error": "Negócio não pôde ser revalidado no MT5 DEMO.", "registered": False,
                                           "reserve_calculated": False, "execution_allowed": False},
                                          request_id, environ)
                if not isinstance(candidate, dict) or not candidate:
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Ticket não encontrado como posição encerrada no histórico MT5 DEMO.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                currency = str(candidate.get("account_currency") or "").strip().upper()
                if currency == "BRL":
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Conta em BRL: use a confirmação Brasil · day trade; este fluxo é para resultados ainda não classificados.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                # The pending queue intentionally accepts valid three-letter
                # currency codes beyond a fixed legacy list (for example NZD).
                # Validate syntax here and preserve jurisdiction/classification
                # as pending; do not infer tax treatment from the currency.
                if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Código de moeda MT5 inválido; resultado não foi salvo.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                if not currency or currency == "UNKNOWN":
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Moeda da conta não identificada; resultado não foi salvo.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                fingerprint = str(candidate.get("account_fingerprint") or "")
                if len(fingerprint) != 32:
                    return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                          {"error": "Identidade da conta MT5 insuficiente para deduplicação segura; informe login e servidor configurados no terminal.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                timestamp = candidate.get("occurred_at_utc")
                if not timestamp:
                    raise ValueError("data do negócio ausente no histórico MT5")
                occurred_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if occurred_at.tzinfo is None:
                    raise ValueError("data do negócio sem fuso horário")
                occurred_on = occurred_at.astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
                reference = f"MT5-DEMO:{fingerprint}:{ticket}"
                components = {
                    "source": "IC Markets MT5 DEMO",
                    "ticket": ticket,
                    "market_scope": "NOT_CONFIRMED",
                    "market_scope_source": "NOT_DECLARED",
                    "independent_market_eligibility_verified": False,
                    "tax_classification_status": "PENDING_CLASSIFICATION",
                    "tax_classification_confirmed_by_user": False,
                    "tax_liability_confirmed": False,
                    "position_id": candidate.get("position_id"),
                    "opened_at_utc": candidate.get("opened_at_utc"),
                    "occurred_at_utc": timestamp,
                    "profit": candidate.get("profit"),
                    "commission": candidate.get("commission"),
                    "swap": candidate.get("swap"),
                    "fee": candidate.get("fee"),
                    "account_currency": currency,
                    "result_scope": "FULL_CLOSED_POSITION",
                    "deal_count": candidate.get("deal_count"),
                    "closing_deal_count": candidate.get("closing_deal_count"),
                    "reconciliation_notice": "Resultado agregado do histórico completo da posição; conferir extrato da corretora antes de qualquer uso fiscal.",
                }
                payload = {
                    "reference": reference,
                    "original_result": candidate.get("net_result_account_currency"),
                    "original_currency": currency,
                    "instrument": str(candidate.get("symbol") or "MT5_INSTRUMENT_UNKNOWN")[:80],
                    "jurisdiction": "PENDING_REVIEW",
                    "institution": "IC Markets MT5 DEMO",
                    "custody_location": "NOT_INFORMED",
                    "contract_type": "NOT_CONFIRMED",
                    "occurred_on": occurred_on,
                    "notes": json.dumps(components, ensure_ascii=False, separators=(",", ":"))[:1000],
                }
                try:
                    item = FISCAL_PENDING_QUEUE.add_realized_result(fiscal_owner_id, payload)
                except sqlite3.IntegrityError:
                    return _json_response(start_response, HTTPStatus.CONFLICT,
                                          {"error": "Este ticket MT5 DEMO já está na fila fiscal desta conta.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                return _json_response(start_response, HTTPStatus.CREATED,
                                      {"pending": item, "source": "IC Markets MT5 DEMO",
                                       "source_ticket": ticket, "registered": True,
                                       "classification_status": "PENDING_CLASSIFICATION",
                                       "reserve_calculated": False, "execution_allowed": False},
                                      request_id, environ)
        if path == "/api/fiscal-reserve/mt5-confirm" and method == "POST":
            data = _read_json(environ)
            if data.get("confirmed") is not True:
                raise ValueError("confirmação explícita obrigatória")
            ticket = str(data.get("ticket") or "").strip()
            if not ticket or len(ticket) > 80:
                raise ValueError("ticket MT5 é obrigatório e deve ter até 80 caracteres")
            category = str(data.get("category") or "").strip().upper()
            if category != "BR_DAY_TRADE":
                raise ValueError("categoria precisa ser confirmada explicitamente como BR_DAY_TRADE")
            if data.get("market_scope") != "BR_ELIGIBLE_MARKET":
                raise ValueError("mercado brasileiro elegível não foi confirmado; mantenha o negócio pendente até classificação")
            declared_market_scope = str(data.get("market_scope") or "").strip()[:80]
            with getattr(SERVICE.mt5_operational_adapter, "session_lock", nullcontext()):
                try:
                    candidate = SERVICE.mt5_operational_adapter.read_closed_deal_candidate(ticket)
                except MT5DealNotFoundError:
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Ticket não encontrado como encerramento integral e conciliado no histórico MT5 DEMO.",
                                           "registered": False, "reserve_calculated": False,
                                           "execution_allowed": False}, request_id, environ)
                except RuntimeError as exc:
                    return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                           {"error": "Negócio não pôde ser revalidado no MT5 DEMO.",
                                            "registered": False, "execution_allowed": False}, request_id, environ)
                if not isinstance(candidate, dict) or not candidate:
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Ticket não encontrado como posição encerrada no histórico MT5 DEMO.",
                                           "registered": False, "classification_status": "PENDING_CLASSIFICATION",
                                           "reserve_calculated": False, "execution_allowed": False},
                                          request_id, environ)
                if str(candidate.get("account_currency", "")).upper() != "BRL":
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Conta MT5 não está em BRL. O negócio deve permanecer pendente até classificação e conversão documentadas.",
                                           "registered": False, "classification_status": "PENDING_CLASSIFICATION",
                                           "reserve_calculated": False, "execution_allowed": False},
                                          request_id, environ)
                timestamp = candidate.get("occurred_at_utc")
                if not timestamp:
                    raise ValueError("data do negócio ausente no histórico MT5")
                occurred_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if occurred_at.tzinfo is None:
                    raise ValueError("data do negócio sem fuso horário")
                occurred_on = occurred_at.astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
                opened_timestamp = candidate.get("opened_at_utc")
                if not opened_timestamp:
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Data de abertura da posição ausente; classificação day trade não foi validada.",
                                           "registered": False, "classification_status": "PENDING_CLASSIFICATION",
                                           "reserve_calculated": False, "execution_allowed": False},
                                          request_id, environ)
                try:
                    opened_at = datetime.fromisoformat(str(opened_timestamp).replace("Z", "+00:00"))
                except ValueError:
                    opened_at = None
                if opened_at is None or opened_at.tzinfo is None:
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "Data de abertura da posição sem fuso horário; classificação day trade não foi validada.",
                                           "registered": False, "classification_status": "PENDING_CLASSIFICATION",
                                           "reserve_calculated": False, "execution_allowed": False},
                                          request_id, environ)
                opened_on = opened_at.astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
                if opened_on != occurred_on:
                    return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                          {"error": "A posição foi aberta e encerrada em dias diferentes; não pode ser registrada como day trade. Mantenha-a pendente para classificação.",
                                           "opened_on": opened_on, "closed_on": occurred_on,
                                           "registered": False, "classification_status": "PENDING_CLASSIFICATION",
                                           "reserve_calculated": False, "execution_allowed": False},
                                          request_id, environ)
                fingerprint = str(candidate.get("account_fingerprint") or "")
                if len(fingerprint) != 32:
                    return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                          {"error": "Identidade da conta MT5 insuficiente para deduplicação segura; informe login e servidor configurados no terminal.",
                                           "registered": False, "execution_allowed": False},
                                          request_id, environ)
                reference = f"MT5-DEMO:{fingerprint}:{ticket}"
                evidence = {
                    "source": "IC Markets MT5 DEMO",
                    "ticket": ticket,
                    "position_id": candidate.get("position_id"),
                    "opened_at_utc": candidate.get("opened_at_utc"),
                    "occurred_at_utc": timestamp,
                    "profit": candidate.get("profit"),
                    "commission": candidate.get("commission"),
                    "swap": candidate.get("swap"),
                    "fee": candidate.get("fee"),
                    "account_currency": "BRL",
                    "result_scope": "FULL_CLOSED_POSITION",
                    "deal_count": candidate.get("deal_count"),
                    "closing_deal_count": candidate.get("closing_deal_count"),
                    "tax_classification_status": "USER_DECLARED_PENDING_REVIEW",
                    "market_scope_source": "USER_DECLARATION_NOT_INDEPENDENTLY_VERIFIED",
                    "declared_market_scope": declared_market_scope,
                    "independent_market_eligibility_verified": False,
                    "tax_liability_confirmed": False,
                    "reserve_semantics": "PLANNING_ESTIMATE_ONLY",
                    "reconciliation_notice": "Resultado agregado do histórico completo da posição; conferir extrato da corretora antes de qualquer uso fiscal. Categoria e elegibilidade de mercado foram declaradas pelo usuário e ainda exigem revisão independente.",
                }
                payload = {
                    "category_candidate": "BR_DAY_TRADE",
                    "instrument": str(candidate.get("symbol") or "INSTRUMENT_NOT_PROVIDED"),
                    "market_scope": declared_market_scope,
                    "realized_result_brl": candidate["net_result_account_currency"],
                    "reference": reference,
                    "occurred_on": occurred_on,
                    "notes": json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))[:1000],
                }
                try:
                    pending = FISCAL_DOMESTIC_PENDING_QUEUE.add(fiscal_owner_id, payload)
                except sqlite3.IntegrityError:
                    return _json_response(start_response, HTTPStatus.CONFLICT,
                                          {"error": "Este ticket MT5 DEMO já está na fila de revisão fiscal brasileira.",
                                           "reference": reference, "registered": False,
                                           "classification_status": "PENDING_CLASSIFICATION",
                                           "reserve_calculated": False, "included_in_totals": False,
                                           "execution_allowed": False}, request_id, environ)
                return _json_response(start_response, HTTPStatus.CREATED,
                                      {"pending": pending, "source": "IC Markets MT5 DEMO",
                                       "source_ticket": ticket, "registered": True,
                                       "classification_status": "PENDING_CLASSIFICATION",
                                       "classification_source": "USER_DECLARATION",
                                       "independent_market_eligibility_verified": False,
                                       "tax_liability_confirmed": False,
                                       "reserve_is_estimate": False,
                                       "reserve_calculated": False, "included_in_totals": False,
                                       "execution_allowed": False}, request_id, environ)
        if path == "/api/fiscal-reserve/mt5-preview" and method == "GET":
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            try:
                lookback_days = int(query.get("lookback_days", ["30"])[-1] or "30")
            except (TypeError, ValueError) as exc:
                raise ValueError("lookback_days deve ser um inteiro") from exc
            if not 1 <= lookback_days <= 365:
                raise ValueError("lookback_days deve estar entre 1 e 365")
            try:
                preview = SERVICE.mt5_operational_adapter.read_closed_deal_candidates(lookback_days=lookback_days)
            except RuntimeError as exc:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Histórico MT5 DEMO indisponível para conferência.", "auto_registered": False}, request_id, environ)
            return _json_response(start_response, HTTPStatus.OK, preview, request_id, environ)
        if path == "/api/fiscal-reserve" and method == "GET":
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            try:
                history_limit = int(query.get("limit", ["100"])[-1] or "100")
                history_offset = int(query.get("offset", ["0"])[-1] or "0")
            except (TypeError, ValueError) as exc:
                raise ValueError("limit e offset devem ser inteiros") from exc
            if not 1 <= history_limit <= 500:
                raise ValueError("limit deve estar entre 1 e 500")
            if not 0 <= history_offset <= MAX_FISCAL_HISTORY_OFFSET:
                raise ValueError(
                    f"offset deve estar entre 0 e {MAX_FISCAL_HISTORY_OFFSET}"
                )
            fiscal_summary = FISCAL_RESERVE.summary(
                fiscal_owner_id, history_limit=history_limit, history_offset=history_offset
            )
            fiscal_summary["classification_catalog"] = fiscal_classification_catalog()
            try:
                fiscal_summary["foreign_pending"] = FISCAL_PENDING_QUEUE.summary(fiscal_owner_id)
            except (sqlite3.Error, RuntimeError, ValueError):
                # The main Brazilian ledger remains readable if an older or
                # independently configured pending-queue database is not migrated.
                # Never substitute guessed counts or include pending items in totals.
                fiscal_summary["foreign_pending"] = {
                    "available": False,
                    "classification_status": "PENDING_CLASSIFICATION",
                    "included_in_totals": False,
                    "reserve_calculated": False,
                }
            # Keep legacy foreign settings in storage for historical compatibility,
            # but never expose the generic percentage as a usable public tax rate.
            foreign = fiscal_summary.get("categories", {}).get("FOREIGN_FINANCIAL_ASSET")
            if isinstance(foreign, dict):
                foreign.pop("rate", None)
                foreign["realized_result_brl"] = 0.0
                foreign["reserve_amount_brl"] = 0.0
                foreign["classification_status"] = "PENDING_CLASSIFICATION"
                foreign["rate_available"] = False
            # Legacy foreign ledger rows remain available for audit, but their
            # historical generic rate/reserve amount must not be presented as valid.
            for entry in fiscal_summary.get("history", []):
                if isinstance(entry, dict) and entry.get("category") == "FOREIGN_FINANCIAL_ASSET":
                    entry.pop("reserve_rate", None)
                    entry.pop("reserve_amount_brl", None)
                    entry["classification_status"] = "PENDING_CLASSIFICATION"
            return _json_response(
                start_response, HTTPStatus.OK, fiscal_summary, request_id, environ
            )
        if path == "/api/fiscal-reserve/rates" and method == "POST":
            data = _read_json(environ)
            if "rates" in data:
                settings = FISCAL_RESERVE.update_rates(fiscal_owner_id, data["rates"])
            else:
                settings = FISCAL_RESERVE.update_rate(fiscal_owner_id, data.get("category"), data.get("rate"))
            # Keep the legacy foreign setting internally for database compatibility,
            # but never expose its generic percentage through the public API.
            settings.pop("FOREIGN_FINANCIAL_ASSET", None)
            return _json_response(start_response, HTTPStatus.OK, {"settings": settings}, request_id, environ)
        if path == "/api/fiscal-reserve/results" and method == "POST":
            data = _read_json(environ)
            if data.get("confirmed") is not True:
                raise ValueError("confirmação explícita dos critérios de day trade é obrigatória")
            def required_text(field: str, label: str, maximum: int) -> str:
                raw = data.get(field)
                if not isinstance(raw, str):
                    raise ValueError(f"{label} deve ser texto")
                value = raw.strip()
                if not value or len(value) > maximum:
                    raise ValueError(f"{label} é obrigatório e deve ter até {maximum} caracteres")
                return value

            instrument = required_text("instrument", "instrumento", 80)
            institution = required_text("institution", "instituição", 120)
            market_label = required_text("market_label", "mercado de negociação", 120)
            raw_notes = data.get("notes", "")
            if not isinstance(raw_notes, str):
                raise ValueError("notes deve ser texto")
            user_notes = raw_notes.strip()
            if len(user_notes) > 160:
                raise ValueError("notes deve ter até 160 caracteres")
            if data.get("market_scope") != "BR_ELIGIBLE_MARKET":
                raise ValueError("mercado brasileiro elegível não foi confirmado")
            if any(data.get(flag) is not True for flag in ("same_asset", "same_institution", "same_day")):
                raise ValueError("mesmo ativo, mesma instituição e mesmo dia precisam ser confirmados")
            notes = {
                "tax_classification_status": "USER_DECLARED_PLANNING_ONLY",
                "classification_source": "USER_DECLARATION",
                "market_scope_source": "USER_DECLARATION_NOT_INDEPENDENTLY_VERIFIED",
                "market_scope": "BR_ELIGIBLE_MARKET",
                "instrument": instrument,
                "institution": institution,
                "market_label": market_label,
                "same_asset_confirmed_by_user": True,
                "same_institution_confirmed_by_user": True,
                "same_day_confirmed_by_user": True,
                "independent_market_eligibility_verified": False,
                "tax_liability_confirmed": False,
                "reserve_semantics": "PLANNING_ESTIMATE_ONLY",
                "user_notes": user_notes,
            }
            evidence_notes = json.dumps(notes, ensure_ascii=False, separators=(",", ":"))
            if len(evidence_notes) > 1000:
                raise ValueError("evidências excedem o limite de armazenamento")
            payload = {
                "category": "BR_DAY_TRADE",
                "realized_result_brl": data.get("realized_result_brl"),
                "reference": data.get("reference"),
                "occurred_on": data.get("occurred_on"),
                "notes": evidence_notes,
            }
            entry = FISCAL_RESERVE.record_realized_result(fiscal_owner_id, payload)
            return _json_response(
                start_response, HTTPStatus.OK,
                {"entry": entry, "classification_status": "USER_DECLARED_PLANNING_ONLY",
                 "classification_source": "USER_DECLARATION",
                 "independent_market_eligibility_verified": False,
                 "tax_liability_confirmed": False, "reserve_is_estimate": True,
                 "execution_allowed": False}, request_id, environ)
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
        if path == "/api/notifications/recovery/inspect" and method == "GET":
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                return _json_response(start_response, _remote_identity_http_status(reason),
                                      {"error": "Identidade autenticada necessária para inspecionar a quarentena."},
                                      request_id, environ)
            archive_ids = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True).get("archive_id", [])
            archive_id = archive_ids[-1].strip() if archive_ids else ""
            if not archive_id:
                raise ValueError("archive_id obrigatório")
            inspected = SERVICE.state_store.inspect_notification_quarantine(archive_id)
            inspected.pop("notifications", None)
            return _json_response(start_response, HTTPStatus.OK,
                                  {"archive": inspected, "execution_allowed": False}, request_id, environ)
        if path == "/api/notifications/recovery/archive" and method == "POST":
            data = _read_json(environ)
            if data.get("confirmed") is not True:
                raise ValueError("confirmação explícita obrigatória")
            archived = SERVICE.state_store.archive_notifications_for_recovery(confirmed=True)
            return _json_response(start_response, HTTPStatus.CREATED,
                                  {"archive": archived, "original_preserved": True,
                                   "execution_allowed": False}, request_id, environ)
        if path == "/api/notifications/recovery/restore" and method == "POST":
            data = _read_json(environ)
            archive_id = data.get("archive_id")
            if not isinstance(archive_id, str) or not archive_id.strip():
                raise ValueError("archive_id obrigatório")
            if data.get("confirmed") is not True:
                raise ValueError("confirmação explícita obrigatória")
            restored = SERVICE.restore_notification_history(
                archive_id.strip(), confirmed=True
            )
            return _json_response(start_response, HTTPStatus.OK,
                                  {"restoration": restored, "execution_allowed": False},
                                  request_id, environ)
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
            executed = data.get("executed")
            if not isinstance(executed, bool):
                return _json_response(
                    start_response,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "executed deve ser booleano verdadeiro ou falso."},
                    request_id,
                    environ,
                )
            REAL_RUNTIME.reconcile(
                request_id=str(data.get("request_id", "")),
                executed=executed,
            )
            return _json_response(start_response, HTTPStatus.OK, {"reconciled": True}, request_id, environ)
        if path == "/api/runtime/real/close/reconcile" and method == "POST":
            data = _read_json(environ)
            result = REAL_RUNTIME.reconcile_position_close(
                request_id=data.get("request_id"),
                external_id=data.get("external_id"),
            )
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {"close_reconciliation": result},
                request_id,
                environ,
            )
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
        if path == "/api/runtime/timed-exits" and method == "GET":
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                status = HTTPStatus.UNAUTHORIZED if reason == "trusted identity is required" else HTTPStatus.SERVICE_UNAVAILABLE
                return _json_response(
                    start_response,
                    status,
                    {"error": "identidade autorizada necessária para consultar saídas temporizadas DEMO", "execution_allowed": False},
                    request_id,
                    environ,
                )
            schedules = SERVICE.list_mt5_timed_exits()
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {"timed_exits": schedules, "count": len(schedules), "read_only": True, "orders_sent": False},
                request_id,
                environ,
            )
        if path == "/api/runtime/positions/recovery/local" and method == "GET":
            authorized, reason = _authorize_local_runtime(environ)
            if not authorized:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": reason}, request_id, environ)
            positions = SERVICE.list_mt5_position_recovery()
            return _json_response(start_response, HTTPStatus.OK, {
                "positions": positions,
                "count": len(positions),
                "read_only": True,
                "broker_query_performed": False,
                "orders_sent": False,
                "access_scope": "loopback_local",
            }, request_id, environ)
        if path == "/api/runtime/close/local/reconcile" and method == "POST":
            authorized, reason = _authorize_local_runtime(environ)
            if not authorized:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": reason}, request_id, environ)
            data = _read_json(environ)
            cycle_id = data.get("cycle_id")
            external_id = data.get("external_id")
            if not isinstance(cycle_id, str) or not cycle_id.strip():
                raise ValueError("cycle_id é obrigatório")
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id é obrigatório")
            result = SERVICE.reconcile_mt5_position_close(cycle_id=cycle_id, external_id=external_id)
            return _json_response(start_response, HTTPStatus.OK, {"close_reconciliation": result}, request_id, environ)
        if path == "/api/runtime/close/local" and method == "POST":
            authorized, reason = _authorize_local_runtime(environ)
            if not authorized:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": reason}, request_id, environ)
            data = _read_json(environ)
            cycle_id = data.get("cycle_id")
            external_id = data.get("external_id")
            if not isinstance(cycle_id, str) or not cycle_id.strip():
                raise ValueError("cycle_id é obrigatório")
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id é obrigatório")
            close_result = SERVICE.close_mt5_position(cycle_id=cycle_id, external_id=external_id)
            return _json_response(start_response, HTTPStatus.OK, {
                "closed": close_result.accepted,
                "close_state": "CLOSED" if close_result.accepted else "UNKNOWN",
                "message": close_result.message,
                "close_external_id": close_result.external_id,
                "reconciliation": None,
            }, request_id, environ)
        if path == "/api/runtime/positions/recovery" and method == "GET":
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                status = HTTPStatus.UNAUTHORIZED if reason == "trusted identity is required" else HTTPStatus.SERVICE_UNAVAILABLE
                return _json_response(
                    start_response,
                    status,
                    {"error": "identidade autorizada necessária para recuperar posições DEMO", "execution_allowed": False},
                    request_id,
                    environ,
                )
            positions = SERVICE.list_mt5_position_recovery()
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {
                    "positions": positions,
                    "count": len(positions),
                    "read_only": True,
                    "broker_query_performed": False,
                    "orders_sent": False,
                },
                request_id,
                environ,
            )
        if path == "/api/runtime/close/reconcile" and method == "POST":
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                status = HTTPStatus.UNAUTHORIZED if reason == "trusted identity is required" else HTTPStatus.SERVICE_UNAVAILABLE
                return _json_response(start_response, status, {"error": "identidade autorizada necessária", "execution_allowed": False}, request_id, environ)
            data = _read_json(environ)
            cycle_id = data.get("cycle_id")
            external_id = data.get("external_id")
            if not isinstance(cycle_id, str) or not cycle_id.strip():
                raise ValueError("cycle_id é obrigatório")
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id é obrigatório")
            result = SERVICE.reconcile_mt5_position_close(cycle_id=cycle_id, external_id=external_id)
            return _json_response(start_response, HTTPStatus.OK, {"close_reconciliation": result}, request_id, environ)
        if path == "/api/runtime/close" and method == "POST":
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                status = HTTPStatus.UNAUTHORIZED if reason == "trusted identity is required" else HTTPStatus.SERVICE_UNAVAILABLE
                return _json_response(start_response, status, {"error": "identidade autorizada necessária", "execution_allowed": False}, request_id, environ)
            data = _read_json(environ)
            external_id = data.get("external_id")
            cycle_id = data.get("cycle_id")
            if not isinstance(cycle_id, str) or not cycle_id.strip():
                raise ValueError("cycle_id é obrigatório")
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id é obrigatório")
            close_result = SERVICE.close_mt5_position(cycle_id=cycle_id, external_id=external_id)
            return _json_response(start_response, HTTPStatus.OK, {
                "closed": close_result.accepted,
                "close_state": "CLOSED" if close_result.accepted else "UNKNOWN",
                "message": close_result.message,
                "close_external_id": close_result.external_id,
                "reconciliation": None,
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
            for flag in ("confirmed", "filters_ok"):
                if flag in data and not isinstance(data[flag], bool):
                    raise ValueError(f"{flag} deve ser booleano JSON")
            # Validate raw JSON types before coercion: bool is an int in Python,
            # and float(True)/int(True) would otherwise silently become sizing data.
            symbol = data.get("symbol", "")
            timeframe = data.get("timeframe", "5m")
            limit = data.get("limit", 100)
            amount = data.get("amount", 0.01)
            duration_seconds = data.get("duration_seconds", 60)
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("symbol é obrigatório")
            if not isinstance(timeframe, str) or not timeframe.strip():
                raise ValueError("timeframe é obrigatório")
            if not isinstance(limit, int) or isinstance(limit, bool) or not 20 <= limit <= 500:
                raise ValueError("limit deve estar entre 20 e 500")
            if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(float(amount)) or float(amount) <= 0:
                raise ValueError("amount deve ser um número finito e positivo em lotes")
            if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool) or not 1 <= duration_seconds <= 86400:
                raise ValueError("duration_seconds deve estar entre 1 e 86400")
            # Confirmation and filter evidence are derived by the server from
            # the pinned MT5 DEMO feed; client booleans are not trusted here.
            mode_block_reason = _mode_execution_block_reason(SERVICE.get_preferences())
            if mode_block_reason:
                from execution.icmarkets_mt5_market_data import MT5MarketDataError
                try:
                    orchestration = SERVICE.analyze_mt5_market(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=limit,
                    )
                except (MT5MarketDataError, RuntimeError) as exc:
                    return _json_response(
                        start_response,
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "dados de mercado indisponíveis", "execution_allowed": False},
                        request_id,
                        environ,
                    )
                return _json_response(
                    start_response,
                    HTTPStatus.OK,
                    {"runtime": _blocked_cycle_payload(orchestration, mode_block_reason), "execution_allowed": False},
                    request_id,
                    environ,
                )
            result = SERVICE.run_mt5_cycle(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                amount=float(amount),
                duration_seconds=duration_seconds,
            )
            if not result.cycles:
                return _json_response(
                    start_response,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "ciclo indisponível",
                        "detail": result.stop_reason or "nenhum ciclo concluído pelo runtime",
                        "stopped": result.stopped,
                        "stop_reason": result.stop_reason,
                        "execution_allowed": False,
                    },
                    request_id,
                    environ,
                )
            cycle = result.cycles[-1]
            execution = cycle.execution
            orchestration = cycle.orchestration
            execution_accepted = execution is not None and execution.accepted is True
            timed_exit = (
                SERVICE.schedule_mt5_timed_exit(cycle, duration_seconds=duration_seconds)
                if execution_accepted
                else {"state": "NOT_APPLICABLE", "scheduled": False, "message": "sem execução aceita"}
            )
            candidate_decision_value = getattr(orchestration.decision.decision, "value", orchestration.decision.decision)
            automation_state = getattr(getattr(cycle.automation_lifecycle, "state", None), "value", None)
            execution_gate_blocked = execution is None and automation_state == "BLOCKED"
            execution_rejected = execution is not None and not execution_accepted
            execution_not_authorized = not execution_accepted
            decision_value = "AGUARDAR" if execution_not_authorized else candidate_decision_value
            candidate_signal = orchestration.analysis.signal.value
            display_signal = candidate_signal if decision_value == "EXECUTAR" and execution_accepted else "AGUARDAR"
            if execution_gate_blocked:
                display_reason = f"Análise concluída; execução bloqueada pelo runtime: {result.stop_reason or 'autorização de execução ausente'}."
            elif execution_rejected:
                rejection_detail = execution.message or getattr(execution.status, "value", "estado não confirmado")
                display_reason = f"Análise concluída; executor não confirmou a execução: {rejection_detail}."
            elif execution is None and candidate_decision_value == "EXECUTAR":
                display_reason = f"Análise concluída; runtime não confirmou uma execução aceita: {result.stop_reason or 'estado de execução indisponível'}."
            else:
                display_reason = (
                    orchestration.analysis.reason
                    if decision_value == "EXECUTAR" and execution_accepted
                    else orchestration.decision.reason
                )
            payload = {
                "stopped": result.stopped,
                "stop_reason": result.stop_reason,
                "analysis_cycle": {
                    "timestamp": orchestration.timestamp.isoformat(),
                    "symbol": orchestration.analysis.symbol,
                    "timeframe": orchestration.analysis.timeframe,
                },
                "decision": decision_value,
                "candidate_decision": candidate_decision_value,
                "signal": display_signal,
                "candidate_signal": candidate_signal,
                "score": orchestration.analysis.score,
                "reason": display_reason,
                "analysis": {
                    "signal": display_signal,
                    "candidate_signal": candidate_signal,
                    "score": orchestration.analysis.score,
                    "reason": orchestration.analysis.reason,
                    "confirmed": orchestration.analysis.confirmed,
                    "symbol": orchestration.analysis.symbol,
                    "timeframe": orchestration.analysis.timeframe,
                },
                "quality": {
                    "score": orchestration.quality.score,
                    "level": orchestration.quality.level.value,
                    "actionable": orchestration.quality.actionable and decision_value == "EXECUTAR",
                },
                "market_context": orchestration.snapshot.market_context.context.value if orchestration.snapshot.market_context else None,
                "market_data_source": orchestration.market_data.source,
                "candles": len(orchestration.market_data.candles),
                "request_id": cycle.plan.request_id if cycle.plan else None,
                "cycle_id": (
                    orchestration.senior_context.cycle_id
                    if orchestration.senior_context is not None
                    else (cycle.automation_lifecycle.cycle_id if cycle.automation_lifecycle is not None else None)
                ),
                "external_id": execution.external_id if execution else None,
                "execution_status": execution.status.value if execution else None,
                "position_close_policy": "TIMED_BEST_EFFORT_DEMO" if timed_exit.get("scheduled") else "MANUAL_EXPLICIT",
                # MT5's order remains GTC; the separate local worker is a
                # best-effort close schedule, not a broker-side expiry.
                "duration_seconds_applied": False,
                "timed_exit_scheduled": bool(timed_exit.get("scheduled")),
                "timed_exit": timed_exit,
                "execution": {"accepted": execution.accepted, "status": execution.status.value, "message": execution.message, "external_id": execution.external_id} if execution else None,
            }
            return _json_response(start_response, HTTPStatus.OK, {"runtime": payload, "execution_allowed": bool(execution and execution.accepted)}, request_id, environ)
        if path == "/api/market/assets" and method == "GET":
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            # The ecosystem's default catalog must include every broker-listed symbol,
            # including instruments hidden from the current Market Watch view.
            include_invisible = (query.get("include_invisible", ["true"])[-1].lower() in {"1", "true", "yes"})
            assets = SERVICE.get_mt5_assets(include_invisible=include_invisible)
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {"source": "IC Markets MT5 DEMO", "count": len(assets), "assets": list(assets)},
                request_id,
                environ,
            )
        if path == "/api/runtime/analysis/latest" and method == "GET":
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                status = HTTPStatus.UNAUTHORIZED if reason == "trusted identity is required" else HTTPStatus.SERVICE_UNAVAILABLE
                return _json_response(
                    start_response,
                    status,
                    {"error": "identidade autorizada necessária para consultar o último sinal", "execution_allowed": False},
                    request_id,
                    environ,
                )
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            symbol = str(query.get("symbol", [""])[-1]).strip().upper()
            timeframe = str(query.get("timeframe", [""])[-1]).strip().lower()
            if bool(symbol) != bool(timeframe):
                raise ValueError("symbol e timeframe devem ser informados juntos")
            record = LATEST_MARKET_ANALYSIS.latest_record(symbol or None, timeframe or None)
            snapshot = record.get("analysis") if record else None
            updated_at = record.get("updated_at") if record else None
            try:
                configured_max_age = int(os.getenv("CONTROLADOR_ANALYSIS_MAX_AGE_SECONDS", "900"))
            except (TypeError, ValueError):
                configured_max_age = 900
            max_age_seconds = max(60, min(86400, configured_max_age))
            age_seconds = None
            fresh = False
            if isinstance(updated_at, str):
                try:
                    saved_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    if saved_at.tzinfo is not None:
                        age_seconds = max(0.0, (datetime.now(saved_at.tzinfo) - saved_at).total_seconds())
                        fresh = age_seconds <= max_age_seconds
                except ValueError:
                    fresh = False
            available = snapshot is not None and fresh
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {
                    "available": available,
                    "analysis": snapshot if available else None,
                    "saved_at": updated_at,
                    "age_seconds": age_seconds,
                    "max_age_seconds": max_age_seconds,
                    "stale": snapshot is not None and not fresh,
                    "unavailable_reason": "ANALYSIS_EXPIRED" if snapshot is not None and not fresh else None,
                    "cache_scope": "PERSISTENT_SQLITE",
                    "execution_allowed": False,
                    "real": "DESABILITADO",
                },
                request_id,
                environ,
            )
        if path == "/api/runtime/analysis" and method == "POST":
            data = _read_json(environ)
            confirmed = data.get("confirmed")
            filters_ok = data.get("filters_ok")
            if confirmed is not None and not isinstance(confirmed, bool):
                raise ValueError("confirmed deve ser booleano JSON ou null")
            if filters_ok is not None and not isinstance(filters_ok, bool):
                raise ValueError("filters_ok deve ser booleano JSON ou null")
            from execution.icmarkets_mt5_market_data import MT5MarketDataError
            try:
                orchestration = SERVICE.analyze_mt5_market(
                    symbol=str(data.get("symbol", "")),
                    timeframe=str(data.get("timeframe", "5m")),
                    limit=int(data.get("limit", 100)),
                    confirmed=confirmed,
                    filters_ok=filters_ok,
                )
            except (MT5MarketDataError, RuntimeError) as exc:
                return _json_response(
                    start_response,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "dados de mercado indisponíveis",
                        "execution_allowed": False,
                    },
                    request_id,
                    environ,
                )
            snapshot = orchestration.snapshot
            decision_value = getattr(orchestration.decision.decision, "value", orchestration.decision.decision)
            candidate_signal = orchestration.analysis.signal.value
            mode_block_reason = _mode_execution_block_reason(SERVICE.get_preferences())
            # Preserve the technical candidate for audit, but show AGUARDAR when
            # market gates, REAL safety, or the unvalidated leverage mode block action.
            display_decision = "AGUARDAR" if mode_block_reason else decision_value
            display_signal = candidate_signal if display_decision == "EXECUTAR" else "AGUARDAR"
            display_reason = (
                mode_block_reason
                if mode_block_reason
                else (orchestration.analysis.reason if decision_value == "EXECUTAR" else orchestration.decision.reason)
            )
            snapshot_data = snapshot.as_dict()
            snapshot_data["candidate_signal"] = snapshot_data.get("candidate_signal") or candidate_signal
            snapshot_data["signal"] = display_signal
            snapshot_data["actionable"] = bool(snapshot_data.get("actionable", False)) and display_decision == "EXECUTAR"
            analysis_payload = {
                "analysis_cycle": {
                    "timestamp": orchestration.timestamp.isoformat(),
                    "symbol": orchestration.analysis.symbol,
                    "timeframe": orchestration.analysis.timeframe,
                },
                "signal": display_signal,
                "score": orchestration.analysis.score,
                "reason": display_reason,
                "decision": display_decision,
                "analysis": {
                    "signal": display_signal,
                    "candidate_signal": candidate_signal,
                    "score": orchestration.analysis.score,
                    "reason": orchestration.analysis.reason,
                    "confirmed": orchestration.analysis.confirmed,
                    "symbol": orchestration.analysis.symbol,
                    "timeframe": orchestration.analysis.timeframe,
                },
                "quality": {
                    "score": orchestration.quality.score,
                    "level": orchestration.quality.level.value,
                    "actionable": orchestration.quality.actionable and display_decision == "EXECUTAR",
                },
                "decision_detail": {
                    "decision": getattr(orchestration.decision.decision, "value", orchestration.decision.decision),
                    "reason": orchestration.decision.reason,
                },
                "snapshot": snapshot_data,
                "market_data": {
                    "source": orchestration.market_data.source,
                    "candles": len(orchestration.market_data.candles),
                    "ohlcv": [
                        {
                            "timestamp": candle.timestamp.isoformat(),
                            "open": candle.open,
                            "high": candle.high,
                            "low": candle.low,
                            "close": candle.close,
                            "volume": candle.volume,
                        }
                        for candle in orchestration.market_data.candles[-120:]
                    ],
                },
                "execution_allowed": False,
            }
            LATEST_MARKET_ANALYSIS.save(
                orchestration.analysis.symbol,
                orchestration.analysis.timeframe,
                analysis_payload,
            )
            return _json_response(start_response, HTTPStatus.OK, analysis_payload, request_id, environ)
        if path == "/api/analyze" and method == "POST":
            record = SERVICE.analyze(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {**record.to_dict(), **serialize_decision_record(record), "execution_allowed": False}, request_id, environ)
        if path == "/api/simulator/mt5/backtest" and method == "POST":
            data = _read_json(environ)
            result = SERVICE.run_mt5_historical_backtest(
                symbol=str(data.get("symbol", "")),
                timeframe=str(data.get("timeframe", "5m")),
                limit=data.get("limit", 200),
                stop_distance=data.get("stop_distance"),
                take_profit_distance=data.get("take_profit_distance"),
                quantity_units=data.get("quantity_units"),
                contract_multiplier=data.get("contract_multiplier", 1.0),
                spread_price_units=data.get("spread_price_units"),
                slippage_price_units_per_side=data.get("slippage_price_units_per_side"),
                commission_quote_per_unit_round_turn=data.get("commission_quote_per_unit_round_turn", 0.0),
                minimum_directional_score=data.get("minimum_directional_score", 80),
            )
            return _json_response(start_response, HTTPStatus.OK, result, request_id, environ)
        if path == "/api/simulator/mt5" and method == "POST":
            data = _read_json(environ)
            result = SERVICE.simulate_mt5_signal_scenario(
                symbol=str(data.get("symbol", "")),
                timeframe=str(data.get("timeframe", "5m")),
                limit=data.get("limit", 100),
                minimum_directional_score=data.get("minimum_directional_score", 70),
            )
            return _json_response(start_response, HTTPStatus.OK, result, request_id, environ)
        if path == "/api/replay/mt5" and method == "POST":
            data = _read_json(environ)
            result = SERVICE.replay_mt5_history(
                symbol=str(data.get("symbol", "")),
                timeframe=str(data.get("timeframe", "5m")),
                limit=data.get("limit", 100),
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
            updated = SERVICE.validate_learning_source(source, content_verified=data.get("content_verified", False), security_checked=data.get("security_checked", False))
            return _json_response(start_response, HTTPStatus.OK, {"source": {**updated.__dict__, "source_type": updated.source_type.value, "status": updated.status.value}, "operation_eligible": False}, request_id, environ)
        if path == "/api/learning/sources/admit" and method == "POST":
            data = _read_json(environ)
            source = SERVICE.learning_sources.get(str(data.get("source_id", "")))
            if source is None:
                raise ValueError("source_id não encontrado")
            updated = SERVICE.admit_learning_knowledge(source, knowledge_validated=data.get("knowledge_validated", False))
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
        if path == "/assistente" and method == "GET":
            return _file_response(start_response, WEB_DIR / "assistant.html", "text/html; charset=utf-8", request_id, environ)
        if path == "/financeiro/reserva-fiscal" and method == "GET":
            return _file_response(start_response, WEB_DIR / "fiscal-reserve.html", "text/html; charset=utf-8", request_id, environ)
        if path in {"/", "/index.html"} and method == "GET":
            return _file_response(start_response, WEB_DIR / "index.html", "text/html; charset=utf-8", request_id, environ)
        if path == "/manifest.webmanifest" and method == "GET":
            return _file_response(start_response, WEB_DIR / "manifest.webmanifest", "application/manifest+json; charset=utf-8", request_id, environ)
    except AssistantUnavailableError as exc:
        payload = {"error": str(exc), "request_id": request_id}
        if isinstance(exc.conversation_id, str) and exc.conversation_id:
            payload["conversation_id"] = exc.conversation_id
        return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, payload, request_id, environ)
    except NotificationHistoryUnavailableError:
        return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Histórico de notificações indisponível; nenhuma nova notificação foi publicada.", "request_id": request_id}, request_id, environ)
    except sqlite3.Error:
        # Database lock/corruption/unavailability must never look like a
        # successful operation or leak SQL/path details to the client.
        return _json_response(
            start_response,
            HTTPStatus.SERVICE_UNAVAILABLE,
            {"error": "Persistência temporariamente indisponível; nenhuma alteração foi confirmada.", "request_id": request_id},
            request_id,
            environ,
        )
    except PermissionError as exc:
        return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": "Ação não autorizada.", "request_id": request_id}, request_id, environ)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Entrada inválida", "request_id": request_id}, request_id, environ)

    headers = [("Content-Type", "text/plain; charset=utf-8")]
    headers.extend(SECURITY.headers(request_id))
    start_response("404 Not Found", headers)
    _audit(environ, request_id, 404)
    return [b"Not Found"]


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Serve requests concurrently and drain them before runtime locks are released."""

    # Request handlers can touch SQLite and MT5. They must finish before
    # server_close returns; otherwise run() could release process locks while
    # a daemon request thread still has access to the shared runtime resources.
    daemon_threads = False
    block_on_close = True


def run(host: str | None = None, port: int | None = None) -> None:
    selected_host = host or os.environ.get("CONTROLADOR_BIND_HOST", "127.0.0.1")
    selected_port = port or int(os.environ.get("PORT", "8000"))
    if not _RUNTIME_PROCESS_LOCK.is_acquired:
        _RUNTIME_PROCESS_LOCK.acquire()
    timed_exit_worker = None
    try:
        # Keep import and worker construction inside the protected startup
        # block: either can fail after the process locks have been acquired.
        from execution.timed_exit_worker import TimedExitWorker

        timed_exit_worker = TimedExitWorker(SERVICE, OPERATIONAL_RUNTIME)
        timed_exit_worker.start()
        with make_server(
            selected_host,
            selected_port,
            application,
            server_class=ThreadingWSGIServer,
        ) as server:
            print(f"Controlador Trading em http://{selected_host}:{selected_port}")
            server.serve_forever()
    finally:
        # If worker shutdown itself fails, retain the process locks (fail
        # closed). If import/construction/startup fails before a worker exists,
        # release the locks acquired by this run attempt.
        if timed_exit_worker is not None:
            timed_exit_worker.stop()
        _RUNTIME_PROCESS_LOCK.release()


if __name__ == "__main__":
    run()
