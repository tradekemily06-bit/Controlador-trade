"""Read-only HTTP API for the independent seven-area analyst application.

The approved Lovable UI can consume this API without changing its design.
No broker-order or money-movement endpoint is defined here.
"""
from __future__ import annotations

import hmac
import json
import os
from http import HTTPStatus
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server
from typing import Any

from security_guard import MAX_BODY_BYTES, SECURITY
from integration.standalone_runtime import StandaloneRuntime
from integration.standalone_foundation_status import standalone_storage_status
from security.identity_boundary import IdentityPolicy
from security.wsgi_identity import trusted_tenant_context_from_wsgi
from security.tenant_context import TenantContext
from data.timeframes import list_supported_timeframes


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _json_response(start_response, status: HTTPStatus, payload: dict[str, Any], request_id: str):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        *SECURITY.headers(request_id),
    ]
    start_response(f"{status.value} {status.phrase}", headers)
    return [body]


def _allowed_frontend_origins() -> set[str]:
    """Return exact browser origins allowed to call the API cross-origin."""
    configured = os.getenv("CONTROLADOR_ALLOWED_ORIGINS", "")
    return {
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    }


def _origin_from_environ(environ) -> str:
    return str(environ.get("HTTP_ORIGIN") or "").strip().rstrip("/")


def _authorized(environ) -> tuple[bool, str]:
    client = str(environ.get("REMOTE_ADDR") or "")
    loopback = client in {"127.0.0.1", "::1"}
    remote_required = os.getenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "").strip().lower() in {
        "1", "true", "yes",
    }
    if loopback and not remote_required:
        return True, "local"
    if not remote_required:
        return False, "acesso remoto desabilitado; configure a fronteira de identidade antes de publicar o aplicativo"
    expected = os.getenv("CONTROLADOR_STANDALONE_ACCESS_TOKEN", "").strip()
    if not expected:
        return False, "token de acesso do aplicativo não configurado"
    authorization = str(environ.get("HTTP_AUTHORIZATION") or "")
    if not authorization.startswith("Bearer "):
        return False, "autorização obrigatória"
    supplied = authorization[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        return False, "autorização negada"

    # A shared API token is only an access gate, not a user identity.
    # Remote production access additionally requires identity claims injected
    # by trusted server-side authentication middleware (never raw HTTP headers).
    middleware_enabled = os.getenv(
        "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE", ""
    ).strip().lower() in {"1", "true", "yes"}
    tenant_context = trusted_tenant_context_from_wsgi(
        environ, middleware_enabled=middleware_enabled
    )
    identity_policy = IdentityPolicy()
    if (
        tenant_context is None
        or not identity_policy.authorize_production_request(
            authenticated=True, tenant_id=tenant_context.tenant_id
        )
    ):
        return False, (
            "identidade remota verificada e tenant são obrigatórios; "
            "token compartilhado sozinho não autentica um usuário"
        )
    return True, "trusted_identity"


def _tenant_context_for_request(environ, authorization_reason: str) -> TenantContext | None:
    """Resolve request scope from trusted remote middleware or configured local identity."""
    if authorization_reason == "trusted_identity":
        return trusted_tenant_context_from_wsgi(environ, middleware_enabled=True)
    if authorization_reason == "local":
        subject_id = os.getenv("CONTROLADOR_SINGLE_USER_IDENTITY", "").strip()
        if not subject_id:
            return None
        return TenantContext(tenant_id="local-single-user", subject_id=subject_id)
    return None


def _mt5_relay_authorized(environ) -> bool:
    expected = os.getenv("CONTROLADOR_MT5_RELAY_TOKEN", "").strip()
    if not expected:
        return False
    authorization = str(environ.get("HTTP_AUTHORIZATION") or "")
    if not authorization.startswith("Bearer "):
        return False
    supplied = authorization[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        return False
    direct_tls = str(environ.get("wsgi.url_scheme", "")).lower() == "https"
    trusted_proxy_tls = (
        os.getenv("CONTROLADOR_TRUST_PROXY_TLS", "").strip().lower() in {"1", "true", "yes"}
        and str(environ.get("HTTP_X_FORWARDED_PROTO", "")).lower() == "https"
    )
    return direct_tls or trusted_proxy_tls


def _read_json(environ) -> dict[str, Any]:
    raw_length = environ.get("CONTENT_LENGTH") or "0"
    try:
        length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("content-length inválido") from exc
    if length < 0 or length > MAX_BODY_BYTES:
        raise ValueError("payload excede o limite permitido")
    raw = environ["wsgi.input"].read(length)
    if len(raw) != length:
        raise ValueError("payload incompleto")
    payload = json.loads(raw or b"{}")
    if not isinstance(payload, dict):
        raise ValueError("payload deve ser um objeto JSON")
    return payload


class StandaloneWSGIApplication:
    def __init__(self, runtime: StandaloneRuntime) -> None:
        if runtime is None or runtime.closed:
            raise ValueError("runtime standalone ativo é obrigatório")
        self.runtime = runtime

    def __call__(self, environ, start_response):
        request_id = SECURITY.request_id()
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        origin = _origin_from_environ(environ)
        allowed_origins = _allowed_frontend_origins()

        # CORS is opt-in and exact-origin only. Never reflect arbitrary origins
        # or accept wildcard origins for an authenticated analyst API.
        if origin and origin not in allowed_origins:
            return _json_response(
                start_response, HTTPStatus.FORBIDDEN,
                {"error": "origem do navegador não autorizada", "execution_authorized": False},
                request_id,
            )

        if origin:
            original_start_response = start_response

            def cors_start_response(status, headers, exc_info=None):
                headers = list(headers)
                headers.extend([
                    ("Access-Control-Allow-Origin", origin),
                    ("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"),
                    ("Access-Control-Allow-Headers", "Authorization, Content-Type"),
                    ("Access-Control-Max-Age", "600"),
                    ("Vary", "Origin"),
                ])
                return original_start_response(status, headers, exc_info)

            start_response = cors_start_response

        if not SECURITY.allow(environ):
            return _json_response(
                start_response, HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "limite de requisições excedido", "execution_authorized": False},
                request_id,
            )


        if method == "OPTIONS":
            if not origin:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "preflight CORS exige origem autorizada", "execution_authorized": False},
                    request_id,
                )
            headers = [
                ("Content-Length", "0"),
                *SECURITY.headers(request_id),
            ]
            start_response("204 No Content", headers)
            return []

        if method == "POST" and path == "/api/bridge/mt5/candles":
            if not _mt5_relay_authorized(environ):
                return _json_response(
                    start_response, HTTPStatus.UNAUTHORIZED,
                    {"error": "ponte MT5 não autorizada ou conexão TLS não confirmada", "execution_authorized": False},
                    request_id,
                )
            relay = getattr(self.runtime, "mt5_relay_store", None)
            if relay is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "provedor mt5_relay não está configurado", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                result = relay.ingest(payload)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.ACCEPTED,
                {**result, "execution_authorized": False},
                request_id,
            )
        authorized, reason = _authorized(environ)
        if not authorized:
            return _json_response(
                start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": reason, "execution_authorized": False},
                request_id,
            )


        if method == "GET" and path == "/api/bridge/mt5/status":
            relay = getattr(self.runtime, "mt5_relay_store", None)
            payload = (
                relay.status()
                if relay is not None
                else {"connected": False, "status": "NOT_CONFIGURED", "execution_authorized": False}
            )
            return _json_response(start_response, HTTPStatus.OK, payload, request_id)

        if method == "GET" and path in {"/api/health", "/api/health/live"}:
            architecture = self.runtime.application.architecture()
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "controlador-standalone-analyst",
                    "architecture": architecture["architecture"],
                    "areas": len(architecture["application_areas"]),
                    "execution_authorized": False,
                },
                request_id,
            )

        if method == "GET" and path == "/api/readiness":
            architecture = self.runtime.application.architecture()
            ecosystem = self.runtime.ecosystem_service
            registry = getattr(self.runtime, "market_data_registry", None)
            monitor = getattr(self.runtime, "market_monitor", None)
            worker = getattr(self.runtime, "notification_worker", None)
            assistant = getattr(self.runtime, "assistant", None)
            news_status = getattr(ecosystem, "news_status", None)
            identity_middleware = os.getenv(
                "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE", ""
            ).strip().lower() in {"1", "true", "yes"}
            readiness = {
                "identity": IdentityPolicy().status(
                    remote_identity_middleware_configured=identity_middleware
                ),
                "architecture": architecture.get("architecture", "UNKNOWN"),
                "areas": len(architecture.get("application_areas", [])),
                "market_data": registry.status(probe_account_mode=False) if registry is not None else {"status": "NOT_CONFIGURED"},
                "market_monitor": monitor.status() if monitor is not None else {"status": "NOT_CONFIGURED", "worker_running": False},
                "news": news_status(limit=1) if callable(news_status) else {"status": "NOT_CONFIGURED", "live": False},
                "assistant": assistant.readiness() if callable(getattr(assistant, "readiness", None)) else {"status": "NOT_CONFIGURED"},
                "decision_memory": (
                    self.runtime.ecosystem_service.store.persistence_status()
                    if callable(getattr(getattr(getattr(self.runtime, "ecosystem_service", None), "store", None), "persistence_status", None))
                    else {"mode": "UNKNOWN", "state": "STATUS_NOT_EXPOSED", "durability_confirmed": False}
                ),
                "notifications": ecosystem.notification_summary() if callable(getattr(ecosystem, "notification_summary", None)) else {"status": "NOT_CONFIGURED"},
                "notification_delivery": worker.status() if worker is not None else {"configured": False, "running": False, "state": "NO_EXTERNAL_SINK_CONFIGURED"},
                "storage_foundation": standalone_storage_status(self.runtime),
                "tenant_state": (
                    self.runtime.tenant_state.readiness()
                    if callable(getattr(getattr(self.runtime, "tenant_state", None), "readiness", None))
                    else {"status": "NOT_CONFIGURED", "production_ready": False}
                ),
                "deployment": "PROCESS_RUNNING_DEPLOYMENT_NOT_VERIFIED",
                "execution_authorized": False,
            }
            return _json_response(start_response, HTTPStatus.OK, readiness, request_id)

        if method == "GET" and path == "/api/intelligence/architecture":
            return _json_response(
                start_response, HTTPStatus.OK,
                self.runtime.application.architecture(),
                request_id,
            )

        if method == "GET" and path == "/api/market-data/providers":
            registry = getattr(self.runtime, "market_data_registry", None)
            payload = registry.status(probe_account_mode=False) if registry is not None else {"status": "NOT_CONFIGURED", "count": 0}
            return _json_response(
                start_response, HTTPStatus.OK,
                {**payload, "execution_authorized": False},
                request_id,
            )

        if method == "GET" and path == "/api/market-data/timeframes":
            registry = getattr(self.runtime, "market_data_registry", None)
            selected = registry.selected() if registry is not None else None
            if selected is None:
                provider_compatibility = {
                    "selected_provider": None,
                    "status": "NO_PROVIDER_SELECTED",
                    "supported": [],
                    "unsupported": [],
                    "note": "Configure e valide uma fonte de mercado antes de monitorar intervalos.",
                }
            else:
                capability_check = getattr(selected.provider, "supports_timeframe", None)
                if callable(capability_check):
                    supported = [
                        timeframe for timeframe in list_supported_timeframes()
                        if capability_check(timeframe)
                    ]
                    unsupported = [
                        timeframe for timeframe in list_supported_timeframes()
                        if timeframe not in supported
                    ]
                    capability_status = "DECLARED_NOT_LIVE_TESTED"
                else:
                    supported = []
                    unsupported = []
                    capability_status = "NOT_DECLARED"
                provider_compatibility = {
                    "selected_provider": selected.provider_id,
                    "status": capability_status,
                    "supported": supported,
                    "unsupported": unsupported,
                    "note": "Compatibilidade declarada pelo adaptador; ainda exige teste real de dados para confirmar disponibilidade.",
                }
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "canonical": list_supported_timeframes(),
                    "platform": list_supported_timeframes(platform_format=True),
                    "limits": {"minutes": [1, 59], "hours": [1, 24], "days": [1, 31], "weeks": [1, 4]},
                    "excluded": {"seconds": "fonte sub-minute não suportada", "months": "intervalos de calendário ainda não implementados"},
                    "parser_support": "NORMALIZATION_ONLY",
                    "provider_compatibility": provider_compatibility,
                    "execution_authorized": False,
                },
                request_id,
            )

        if method == "GET" and path == "/api/market-monitor/status":
            monitor = getattr(self.runtime, "market_monitor", None)
            payload = (
                monitor.status()
                if monitor is not None
                else {
                    "enabled": 0,
                    "total": 0,
                    "worker_running": False,
                    "status": "MARKET_DATA_PROVIDER_NOT_CONFIGURED",
                    "execution_authorized": False,
                    "subscriptions": [],
                }
            )
            return _json_response(start_response, HTTPStatus.OK, payload, request_id)

        if method == "GET" and path == "/api/market-monitor/results":
            monitor = getattr(self.runtime, "market_monitor", None)
            if monitor is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "fonte de dados de mercado não configurada", "results": [], "execution_authorized": False},
                    request_id,
                )
            try:
                query = str(environ.get("QUERY_STRING") or "")
                params = dict(
                    item.split("=", 1) for item in query.split("&")
                    if item and "=" in item
                )
                limit = int(params.get("limit", "50"))
                results = monitor.latest_results(limit=limit)
            except (ValueError, TypeError):
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": "limit deve ser um inteiro entre 1 e 200", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {"results": results, "execution_authorized": False},
                request_id,
            )

        if method == "GET" and path == "/api/market-monitor/subscriptions":
            monitor = getattr(self.runtime, "market_monitor", None)
            subscriptions = monitor.subscriptions() if monitor is not None else []
            return _json_response(
                start_response, HTTPStatus.OK,
                {"subscriptions": subscriptions, "execution_authorized": False},
                request_id,
            )

        if method == "POST" and path == "/api/market-monitor/subscriptions":
            monitor = getattr(self.runtime, "market_monitor", None)
            if monitor is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "fonte de dados de mercado não configurada", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                subscription = monitor.subscribe(
                    symbol=payload.get("symbol"),
                    timeframe=payload.get("timeframe"),
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.CREATED,
                {"subscription": subscription, "execution_authorized": False},
                request_id,
            )

        if method == "DELETE" and path == "/api/market-monitor/subscriptions":
            monitor = getattr(self.runtime, "market_monitor", None)
            if monitor is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "fonte de dados de mercado não configurada", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                removed = monitor.unsubscribe(
                    symbol=payload.get("symbol"),
                    timeframe=payload.get("timeframe"),
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {"disabled": removed, "execution_authorized": False},
                request_id,
            )

        if path == "/api/user/preferences" and method in {"GET", "PUT"}:
            tenant_state = getattr(self.runtime, "tenant_state", None)
            if tenant_state is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "armazenamento individual não configurado", "execution_authorized": False},
                    request_id,
                )
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para acessar preferências", "execution_authorized": False},
                    request_id,
                )
            try:
                if method == "GET":
                    preferences = tenant_state.load_preferences(tenant_context) or {}
                    return _json_response(
                        start_response, HTTPStatus.OK,
                        {"preferences": preferences, "scope": "TENANT_SCOPED", "execution_authorized": False},
                        request_id,
                    )
                payload = _read_json(environ)
                preferences = payload.get("preferences")
                if not isinstance(preferences, dict):
                    raise ValueError("preferences deve ser um objeto")
                tenant_state.save_preferences(tenant_context, preferences)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {"preferences": preferences, "scope": "TENANT_SCOPED", "execution_authorized": False},
                request_id,
            )

        if method == "GET" and path == "/api/notifications":
            try:
                query = str(environ.get("QUERY_STRING") or "")
                params = dict(
                    item.split("=", 1) for item in query.split("&")
                    if item and "=" in item
                )
                limit = int(params.get("limit", "50"))
                if not 1 <= limit <= 200:
                    raise ValueError
                include_info = str(params.get("include_info", "false")).lower() in {"1", "true", "yes"}
                items = self.runtime.ecosystem_service.notification_items(include_info=include_info)
            except (ValueError, TypeError):
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": "limit deve ser um inteiro entre 1 e 200", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {"notifications": items[:limit], "count": min(len(items), limit), "execution_authorized": False},
                request_id,
            )

        if method == "GET" and path == "/api/notifications/status":
            summary = self.runtime.ecosystem_service.notification_summary()
            worker = getattr(self.runtime, "notification_worker", None)
            summary["delivery_worker"] = worker.status() if worker is not None else {
                "configured": False,
                "running": False,
                "state": "NO_EXTERNAL_SINK_CONFIGURED",
            }
            summary["external_delivery"] = (
                "WORKER_CONFIGURED" if worker is not None
                else "OUTBOX_ONLY_NO_PROVIDER"
            )
            return _json_response(
                start_response, HTTPStatus.OK,
                {**summary, "execution_authorized": False},
                request_id,
            )

        if method == "GET" and path == "/api/assistant/status":
            readiness = self.runtime.assistant.readiness()
            return _json_response(
                start_response, HTTPStatus.OK,
                {**readiness, "execution_authorized": False},
                request_id,
            )

        if method == "GET" and path == "/api/areas":
            architecture = self.runtime.application.architecture()
            return _json_response(
                start_response, HTTPStatus.OK,
                {"areas": architecture["application_areas"], "execution_authorized": False},
                request_id,
            )

        if method == "POST" and path == "/api/intelligence/route":
            try:
                payload = _read_json(environ)
                area = payload.get("area")
                task = payload.get("task")
                if not isinstance(area, str) or not isinstance(task, str):
                    raise ValueError("area e task são obrigatórios e devem ser textos")
                context = payload.get("context", {})
                if not isinstance(context, dict):
                    raise ValueError("context deve ser um objeto")
                result = self.runtime.application.handle(area=area, task=task, context=context)
            except (ValueError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "serviço indisponível; nenhuma operação foi enviada", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {"result": result, "execution_authorized": False},
                request_id,
            )

        return _json_response(
            start_response, HTTPStatus.NOT_FOUND,
            {"error": "endpoint não encontrado", "execution_authorized": False},
            request_id,
        )


def create_application(runtime: StandaloneRuntime | None = None):
    owned_runtime = runtime or StandaloneRuntime.from_environment()
    return StandaloneWSGIApplication(owned_runtime)


def main() -> None:
    runtime = StandaloneRuntime.from_environment()
    application = StandaloneWSGIApplication(runtime)
    host = os.getenv("CONTROLADOR_BIND_HOST", "127.0.0.1")
    port = int(os.getenv("CONTROLADOR_BIND_PORT", "8765"))
    server = make_server(host, port, application, server_class=ThreadingWSGIServer)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.close()


if __name__ == "__main__":
    main()
