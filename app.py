from __future__ import annotations

import hmac
import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

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
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_taxonomy import fiscal_classification_catalog
from finance.fiscal_pending_queue import CURRENCIES, FiscalPendingQueue
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_schema import migrate_fiscal_schema
from finance.fiscal_identity import FiscalOwnerIdentityError
from assistant.conversation_store import AssistantConversationStore
from assistant.chat_service import EcosystemAssistant, AssistantUnavailableError

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
FISCAL_RESERVE_DB = Path(os.environ.get("CONTROLADOR_FISCAL_RESERVE_DB", str(RUNTIME_DIR / "fiscal-reserve.sqlite3")))
FISCAL_RESERVE = FiscalReserve(str(FISCAL_RESERVE_DB))
FISCAL_PENDING_QUEUE = FiscalPendingQueue(str(FISCAL_RESERVE_DB))
FISCAL_DOMESTIC_PENDING_QUEUE = FiscalDomesticPendingQueue(str(FISCAL_RESERVE_DB))
ASSISTANT_DB = Path(os.environ.get('CONTROLADOR_ASSISTANT_DB', str(RUNTIME_DIR / 'assistant.sqlite3')))
ASSISTANT_STORE = AssistantConversationStore(ASSISTANT_DB)
ASSISTANT = EcosystemAssistant(ASSISTANT_STORE, SERVICE, FISCAL_RESERVE, fiscal_pending_queue=FISCAL_PENDING_QUEUE, fiscal_domestic_pending_queue=FISCAL_DOMESTIC_PENDING_QUEUE)


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
        host = str(environ.get("HTTP_HOST") or "").split(":", 1)[0].strip().lower()
        if host and host not in local_hosts:
            return False, "local host is not allowed"
        return True, "local"

    if not remote_access_required:
        return False, "trusted remote identity provider is not configured"

    if not identity_header:
        return False, "trusted identity header is not configured"

    identity = str(environ.get("HTTP_" + identity_header.upper().replace("-", "_")) or "").strip()
    if not identity:
        return False, "trusted identity is required"

    # Optional single-user pin: when configured, every remote fiscal/assistant
    # request must resolve to this exact normalized Access identity.
    expected_identity = os.environ.get("CONTROLADOR_SINGLE_USER_IDENTITY", "").strip()
    if not expected_identity:
        return False, "single-user identity is not configured"
    if identity.casefold() != expected_identity.casefold():
        return False, "authenticated identity is not authorized for this single-user runtime"

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
                status = HTTPStatus.UNAUTHORIZED if reason == "trusted identity is required" else HTTPStatus.SERVICE_UNAVAILABLE
                return _json_response(
                    start_response,
                    status,
                    {"error": reason, "request_id": request_id},
                    request_id,
                    environ,
                )

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
        if path == "/api/health" and method == "GET":
            status = SERVICE.system_status()
            status["real_runtime"] = REAL_RUNTIME.status()
            return _json_response(start_response, HTTPStatus.OK, {"ok": True, **status}, request_id, environ)
        if path == "/api/status" and method == "GET":
            status = SERVICE.system_status()
            status["real_runtime"] = REAL_RUNTIME.status()
            return _json_response(start_response, HTTPStatus.OK, status, request_id, environ)
        if path.startswith("/api/assistant/"):
            authorized, auth_reason = _authorize_remote_mutation(environ)
            if not authorized:
                auth_status = HTTPStatus.UNAUTHORIZED if auth_reason == "trusted identity is required" else HTTPStatus.FORBIDDEN
                public_reason = (
                    "Identidade autenticada necessária."
                    if auth_reason == "trusted identity is required"
                    else "Identidade autenticada não autorizada para este runtime."
                    if "not authorized for this single-user runtime" in auth_reason
                    else auth_reason
                )
                return _json_response(start_response, auth_status, {"error": public_reason}, request_id, environ)
            try:
                fiscal_owner_id = migrate_fiscal_schema(str(FISCAL_RESERVE_DB))
            except (FiscalOwnerIdentityError, RuntimeError) as exc:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                      {"error": "Reserva Fiscal indisponível até validar a identidade proprietária e a migração.",
                                       "detail": str(exc)}, request_id, environ)
            # A identidade canônica mantém o mesmo espaço de conversas no acesso
            # local e remoto autorizado, sem confiar no valor enviado pelo navegador.
            identity = fiscal_owner_id
            if path == "/api/assistant/status" and method == "GET":
                return _json_response(start_response, HTTPStatus.OK, ASSISTANT.readiness(), request_id, environ)
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
                return _json_response(start_response, HTTPStatus.OK, {"messages": ASSISTANT.history(identity, query)}, request_id, environ)
            if path == "/api/assistant/chat" and method == "POST":
                data = _read_json(environ)
                return _json_response(start_response, HTTPStatus.OK, ASSISTANT.ask(identity, data.get("message"), fiscal_owner_id, data.get("conversation_id")), request_id, environ)
        if path.startswith("/api/fiscal-reserve"):
            authorized, reason = _authorize_remote_mutation(environ)
            if not authorized:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": reason, "request_id": request_id}, request_id, environ)
            try:
                fiscal_owner_id = migrate_fiscal_schema(str(FISCAL_RESERVE_DB))
            except (FiscalOwnerIdentityError, RuntimeError) as exc:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                      {"error": "Reserva Fiscal indisponível até validar a identidade proprietária e a migração.",
                                       "detail": str(exc)}, request_id, environ)
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
                return _json_response(start_response, HTTPStatus.OK,
                                      {"reviews": FISCAL_DOMESTIC_PENDING_QUEUE.list_reviews(fiscal_owner_id, pending_id),
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
                return _json_response(start_response, HTTPStatus.OK,
                                      {"reviews": FISCAL_PENDING_QUEUE.list_reviews(fiscal_owner_id, pending_id),
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
            try:
                candidate = SERVICE.mt5_operational_adapter.read_closed_deal_candidate(ticket)
            except RuntimeError as exc:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                      {"error": "Negócio não pôde ser revalidado no MT5 DEMO.",
                                       "detail": str(exc), "registered": False,
                                       "reserve_calculated": False, "execution_allowed": False},
                                      request_id, environ)
            currency = str(candidate.get("account_currency") or "").strip().upper()
            if currency == "BRL":
                return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                      {"error": "Conta em BRL: use a confirmação Brasil · day trade; este fluxo é para resultados ainda não classificados.",
                                       "registered": False, "reserve_calculated": False,
                                       "execution_allowed": False}, request_id, environ)
            if currency not in CURRENCIES:
                return _json_response(start_response, HTTPStatus.UNPROCESSABLE_ENTITY,
                                      {"error": "Moeda da conta MT5 não suportada pela fila fiscal; resultado não foi salvo.",
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
                "market_scope": "BR_ELIGIBLE_MARKET",
                "tax_classification_confirmed_by_user": True,
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
            category = str(data.get("category") or "").strip().upper()
            if category != "BR_DAY_TRADE":
                raise ValueError("categoria precisa ser confirmada explicitamente como BR_DAY_TRADE")
            if data.get("market_scope") != "BR_ELIGIBLE_MARKET":
                raise ValueError("mercado brasileiro elegível não foi confirmado; mantenha o negócio pendente até classificação")
            declared_market_scope = str(data.get("market_scope") or "").strip()[:80]
            try:
                candidate = SERVICE.mt5_operational_adapter.read_closed_deal_candidate(ticket)
            except RuntimeError as exc:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                       {"error": "Negócio não pôde ser revalidado no MT5 DEMO.", "detail": str(exc),
                                        "registered": False, "execution_allowed": False}, request_id, environ)
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
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Histórico MT5 DEMO indisponível para conferência.", "detail": str(exc), "auto_registered": False}, request_id, environ)
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
            if history_offset < 0:
                raise ValueError("offset deve ser não negativo")
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
                settings = FISCAL_RESERVE.update_rate(fiscal_owner_id, str(data.get("category", "")), data.get("rate"))
            # Keep the legacy foreign setting internally for database compatibility,
            # but never expose its generic percentage through the public API.
            settings.pop("FOREIGN_FINANCIAL_ASSET", None)
            return _json_response(start_response, HTTPStatus.OK, {"settings": settings}, request_id, environ)
        if path == "/api/fiscal-reserve/results" and method == "POST":
            data = _read_json(environ)
            if data.get("confirmed") is not True:
                raise ValueError("confirmação explícita dos critérios de day trade é obrigatória")
            instrument = str(data.get("instrument") or "").strip()
            institution = str(data.get("institution") or "").strip()
            market_label = str(data.get("market_label") or "").strip()
            if not instrument or len(instrument) > 80:
                raise ValueError("instrumento é obrigatório e deve ter até 80 caracteres")
            if not institution or len(institution) > 120:
                raise ValueError("instituição é obrigatória e deve ter até 120 caracteres")
            if not market_label or len(market_label) > 120:
                raise ValueError("mercado de negociação é obrigatório e deve ter até 120 caracteres")
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
                "user_notes": str(data.get("notes") or "").strip()[:160],
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
            confirmed = data.get("confirmed", False)
            filters_ok = data.get("filters_ok", True)
            if not isinstance(confirmed, bool) or not isinstance(filters_ok, bool):
                raise ValueError("confirmed e filters_ok devem ser booleanos JSON")
            mode_block_reason = _mode_execution_block_reason(SERVICE.get_preferences())
            if mode_block_reason:
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
                        {"error": "dados de mercado indisponíveis", "detail": str(exc), "execution_allowed": False},
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
                symbol=str(data.get("symbol", "")),
                timeframe=str(data.get("timeframe", "5m")),
                limit=int(data.get("limit", 100)),
                amount=float(data.get("amount", 0.01)),
                duration_seconds=int(data.get("duration_seconds", 60)),
                confirmed=confirmed,
                filters_ok=filters_ok,
                entry_conditions=tuple(data.get("entry_conditions", ()) or ()),
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
            decision_value = getattr(orchestration.decision.decision, "value", orchestration.decision.decision)
            candidate_signal = orchestration.analysis.signal.value
            display_signal = candidate_signal if decision_value == "EXECUTAR" else "AGUARDAR"
            display_reason = (
                orchestration.analysis.reason
                if decision_value == "EXECUTAR"
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
                "execution": {"accepted": execution.accepted, "status": execution.status.value, "message": execution.message, "external_id": execution.external_id} if execution else None,
            }
            return _json_response(start_response, HTTPStatus.OK, {"runtime": payload, "execution_allowed": bool(execution and execution.accepted)}, request_id, environ)
        if path == "/api/market/assets" and method == "GET":
            query = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
            include_invisible = (query.get("include_invisible", ["false"])[-1].lower() in {"1", "true", "yes"})
            assets = SERVICE.get_mt5_assets(include_invisible=include_invisible)
            return _json_response(
                start_response,
                HTTPStatus.OK,
                {"source": "IC Markets MT5 DEMO", "count": len(assets), "assets": list(assets)},
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
                        "detail": str(exc),
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
            return _json_response(start_response, HTTPStatus.OK, {
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
            }, request_id, environ)
        if path == "/api/analyze" and method == "POST":
            record = SERVICE.analyze(_read_json(environ))
            return _json_response(start_response, HTTPStatus.OK, {**record.to_dict(), **serialize_decision_record(record), "execution_allowed": False}, request_id, environ)
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
        if path == "/assistente" and method == "GET":
            return _file_response(start_response, WEB_DIR / "assistant.html", "text/html; charset=utf-8", request_id, environ)
        if path == "/financeiro/reserva-fiscal" and method == "GET":
            return _file_response(start_response, WEB_DIR / "fiscal-reserve.html", "text/html; charset=utf-8", request_id, environ)
        if path in {"/", "/index.html"} and method == "GET":
            return _file_response(start_response, WEB_DIR / "index.html", "text/html; charset=utf-8", request_id, environ)
        if path == "/manifest.webmanifest" and method == "GET":
            return _file_response(start_response, WEB_DIR / "manifest.webmanifest", "application/manifest+json; charset=utf-8", request_id, environ)
    except AssistantUnavailableError as exc:
        return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc), "request_id": request_id}, request_id, environ)
    except PermissionError as exc:
        return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "request_id": request_id}, request_id, environ)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Entrada inválida", "request_id": request_id}, request_id, environ)

    headers = [("Content-Type", "text/plain; charset=utf-8")]
    headers.extend(SECURITY.headers(request_id))
    start_response("404 Not Found", headers)
    _audit(environ, request_id, 404)
    return [b"Not Found"]


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Serve each request independently so a slow route cannot block local health probes."""

    daemon_threads = True
    block_on_close = False


def run(host: str | None = None, port: int | None = None) -> None:
    selected_host = host or os.environ.get("CONTROLADOR_BIND_HOST", "127.0.0.1")
    selected_port = port or int(os.environ.get("PORT", "8000"))
    lock = RuntimeProcessLock(RUNTIME_DIR / "controlador-runtime.lock")
    with lock:
        with make_server(
            selected_host,
            selected_port,
            application,
            server_class=ThreadingWSGIServer,
        ) as server:
            print(f"Controlador Trading em http://{selected_host}:{selected_port}")
            server.serve_forever()


if __name__ == "__main__":
    run()
