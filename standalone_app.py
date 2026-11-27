"""Read-only HTTP API for the independent seven-area analyst application.

The approved Lovable UI can consume this API without changing its design.
No broker-order or money-movement endpoint is defined here.
"""
from __future__ import annotations

import hmac
import json
import os
import re
from http import HTTPStatus
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server
from typing import Any
from urllib.parse import parse_qs

from security_guard import MAX_BODY_BYTES, SECURITY
from integration.standalone_runtime import StandaloneRuntime
from integration.standalone_foundation_status import standalone_storage_status
from security.identity_boundary import IdentityPolicy
from security.wsgi_identity import trusted_tenant_context_from_wsgi
from security.tenant_context import TenantContext
from data.timeframes import list_supported_timeframes
from analysis.tenant_decision_analytics import summarize_tenant_decisions, build_tenant_decision_report


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


def _tenant_mt5_relay_identity(environ, resolver):
    """Resolve a per-account relay bearer token to a trusted owner and connection."""
    if resolver is None or not callable(getattr(resolver, "resolve", None)):
        return None
    authorization = str(environ.get("HTTP_AUTHORIZATION") or "")
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not token or len(token) > 512:
        return None
    direct_tls = str(environ.get("wsgi.url_scheme", "")).lower() == "https"
    trusted_proxy_tls = (
        os.getenv("CONTROLADOR_TRUST_PROXY_TLS", "").strip().lower() in {"1", "true", "yes"}
        and str(environ.get("HTTP_X_FORWARDED_PROTO", "")).lower() == "https"
    )
    if not (direct_tls or trusted_proxy_tls):
        return None
    try:
        resolved = resolver.resolve(token)
    except Exception:
        return None
    if not isinstance(resolved, tuple) or len(resolved) != 2:
        return None
    context, connection_id = resolved
    if not isinstance(context, TenantContext):
        return None
    if not isinstance(connection_id, str) or not re.fullmatch(r"[a-f0-9]{32}", connection_id):
        return None
    return context, connection_id


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

        webhook_prefix = "/api/webhooks/tradingview/"
        if method == "POST" and path.startswith(webhook_prefix):
            connection_id = path[len(webhook_prefix):].strip("/")
            vault = getattr(self.runtime, "tenant_tradingview_webhook_vault", None)
            inbox = getattr(self.runtime, "tenant_tradingview_alert_inbox", None)
            direct_tls = str(environ.get("wsgi.url_scheme", "")).lower() == "https"
            trusted_proxy_tls = (
                os.getenv("CONTROLADOR_TRUST_PROXY_TLS", "").strip().lower() in {"1", "true", "yes"}
                and str(environ.get("HTTP_X_FORWARDED_PROTO", "")).lower() == "https"
            )
            if not (direct_tls or trusted_proxy_tls):
                return _json_response(start_response, HTTPStatus.UNAUTHORIZED, {"error": "webhook TradingView exige HTTPS", "execution_authorized": False}, request_id)
            if vault is None or inbox is None:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "webhook TradingView não provisionado", "execution_authorized": False}, request_id)
            try:
                payload = _read_json(environ)
                resolved = vault.resolve_secret(payload.get("secret"))
                if not isinstance(resolved, tuple) or len(resolved) != 2:
                    return _json_response(start_response, HTTPStatus.UNAUTHORIZED, {"error": "segredo do webhook inválido", "execution_authorized": False}, request_id)
                context, token_connection_id = resolved
                if token_connection_id != connection_id:
                    return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": "segredo não pertence à conexão solicitada", "execution_authorized": False}, request_id)
                result = inbox.ingest(context, connection_id, payload)
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "falha ao receber alerta TradingView", "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.ACCEPTED, result, request_id)

        tenant_mt5_prefix = "/api/bridge/mt5/connections/"
        if method == "POST" and path.startswith(tenant_mt5_prefix) and path.endswith("/candles"):
            connection_id = path[len(tenant_mt5_prefix):-len("/candles")].strip("/")
            relay_identity = _tenant_mt5_relay_identity(
                environ, getattr(self.runtime, "tenant_mt5_relay_token_resolver", None)
            )
            if relay_identity is None:
                return _json_response(
                    start_response, HTTPStatus.UNAUTHORIZED,
                    {"error": "token de relay por conta inválido ou TLS não confirmado", "execution_authorized": False},
                    request_id,
                )
            context, token_connection_id = relay_identity
            if connection_id != token_connection_id:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "token não pertence à conexão solicitada", "execution_authorized": False},
                    request_id,
                )
            relay_registry = getattr(self.runtime, "tenant_mt5_relay_registry", None)
            if relay_registry is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "relay MT5 por conta não provisionado no servidor", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                result = relay_registry.ingest(context, connection_id, payload)
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "falha ao receber candles da conta MT5", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.ACCEPTED,
                {**result, "connection_id": connection_id, "read_only": True, "execution_authorized": False},
                request_id,
            )

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

        # cTrader redirects the authorization code to this public HTTPS callback.
        # The one-time state resolves the owner and connection server-side.
        if method == "GET" and path == "/api/oauth/ctrader/callback":
            direct_tls = str(environ.get("wsgi.url_scheme", "")).lower() == "https"
            trusted_proxy_tls = (
                os.getenv("CONTROLADOR_TRUST_PROXY_TLS", "").strip().lower() in {"1", "true", "yes"}
                and str(environ.get("HTTP_X_FORWARDED_PROTO", "")).lower() == "https"
            )
            oauth_service = getattr(self.runtime, "tenant_ctrader_oauth_service", None)
            if not (direct_tls or trusted_proxy_tls):
                return _json_response(start_response, HTTPStatus.UNAUTHORIZED, {"error": "callback cTrader exige HTTPS", "execution_authorized": False}, request_id)
            if oauth_service is None:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "OAuth cTrader não configurado com KMS e cliente de troca", "execution_authorized": False}, request_id)
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            state = query.get("state", [""])[0]
            code = query.get("code", [""])[0]
            if query.get("error"):
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "autorização cTrader recusada pelo titular", "execution_authorized": False}, request_id)
            try:
                result = oauth_service.complete_callback(state=state, code=code)
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "falha segura ao concluir OAuth cTrader", "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.OK, result, request_id)

        authorized, reason = _authorized(environ)
        if not authorized:
            return _json_response(
                start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": reason, "execution_authorized": False},
                request_id,
            )

        # Dedicated market analysis, monitor, memory, statistics and report APIs
        # are tenant-scoped. The generic cross-area route remains blocked.
        if reason == "trusted_identity" and path == "/api/intelligence/route":
            return _json_response(
                start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "recurso compartilhado bloqueado até o isolamento por usuário estar implementado",
                    "state": "TENANT_ISOLATION_NOT_IMPLEMENTED",
                    "execution_authorized": False,
                },
                request_id,
            )


        if method == "POST" and path == "/api/market-data/ctrader-oauth-connections":
            context = _tenant_context_for_request(environ, reason)
            oauth_service = getattr(self.runtime, "tenant_ctrader_oauth_service", None)
            if context is None or oauth_service is None:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "identidade ou OAuth cTrader não configurado", "execution_authorized": False}, request_id)
            try:
                payload = _read_json(environ)
                if set(payload) != {"account_alias"}:
                    raise ValueError("envie somente account_alias; credenciais e tokens são tratados pelo servidor")
                result = oauth_service.provision(context, account_alias=payload["account_alias"])
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "não foi possível provisionar a conexão OAuth cTrader", "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.CREATED, result, request_id)

        ctrader_accounts_prefix = "/api/market-data/connections/"
        ctrader_accounts_suffix = "/ctrader-accounts"
        if method == "GET" and path.startswith(ctrader_accounts_prefix) and path.endswith(ctrader_accounts_suffix):
            context = _tenant_context_for_request(environ, reason)
            account_service = getattr(self.runtime, "tenant_ctrader_account_service", None)
            connection_id = path[len(ctrader_accounts_prefix):-len(ctrader_accounts_suffix)].strip("/")
            if context is None or account_service is None:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "identidade ou seleção segura de conta cTrader indisponível", "execution_authorized": False}, request_id)
            try:
                result = account_service.list_demo_accounts(context, connection_id=connection_id)
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "não foi possível listar contas DEMO cTrader", "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.OK, result, request_id)

        ctrader_account_suffix = "/ctrader-account"
        if method == "POST" and path.startswith(ctrader_accounts_prefix) and path.endswith(ctrader_account_suffix):
            context = _tenant_context_for_request(environ, reason)
            account_service = getattr(self.runtime, "tenant_ctrader_account_service", None)
            connection_id = path[len(ctrader_accounts_prefix):-len(ctrader_account_suffix)].strip("/")
            if context is None or account_service is None:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "identidade ou seleção segura de conta cTrader indisponível", "execution_authorized": False}, request_id)
            try:
                payload = _read_json(environ)
                if set(payload) != {"account_id"}:
                    raise ValueError("envie somente account_id; tokens e credenciais permanecem no servidor")
                result = account_service.connect_demo(
                    context, connection_id=connection_id, account_id=payload["account_id"]
                )
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "não foi possível verificar e conectar a conta DEMO cTrader", "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.OK, result, request_id)

        if method == "POST" and path.startswith("/api/market-data/connections/") and path.endswith("/ctrader-oauth"):
            context = _tenant_context_for_request(environ, reason)
            oauth_service = getattr(self.runtime, "tenant_ctrader_oauth_service", None)
            connection_id = path[len("/api/market-data/connections/"):-len("/ctrader-oauth")].strip("/")
            if context is None or oauth_service is None:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "identidade ou OAuth cTrader não configurado", "execution_authorized": False}, request_id)
            try:
                result = oauth_service.begin(context, connection_id=connection_id)
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "não foi possível iniciar OAuth cTrader", "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.OK, result, request_id)

        if method == "POST" and path == "/api/market-data/tradingview-webhook-connections":
            context = _tenant_context_for_request(environ, reason)
            onboarding = getattr(self.runtime, "tenant_tradingview_webhook_onboarding", None)
            if context is None or onboarding is None:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "identidade ou provisionador TradingView indisponível", "execution_authorized": False}, request_id)
            try:
                payload = _read_json(environ)
                if set(payload) != {"account_alias"}:
                    raise ValueError("envie somente account_alias; segredo do webhook é gerado pelo servidor")
                result = onboarding.provision(context, account_alias=payload["account_alias"])
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "não foi possível provisionar webhook TradingView", "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.CREATED, result, request_id)

        if method == "POST" and path == "/api/market-data/mt5-relay-connections":
            context = _tenant_context_for_request(environ, reason)
            onboarding = getattr(self.runtime, "tenant_mt5_relay_onboarding", None)
            if context is None or onboarding is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "identidade ou provisionador seguro de relay indisponível", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                if set(payload) != {"account_alias"}:
                    raise ValueError("envie somente account_alias; tokens são gerados pelo servidor")
                result = onboarding.provision(context, account_alias=payload["account_alias"])
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "não foi possível provisionar o relay MT5", "execution_authorized": False},
                    request_id,
                )
            return _json_response(start_response, HTTPStatus.CREATED, result, request_id)

        tv_alert_prefix = "/api/market-data/connections/"
        tv_alert_suffix = "/tradingview-alerts"
        if method == "GET" and path.startswith(tv_alert_prefix) and path.endswith(tv_alert_suffix):
            context = _tenant_context_for_request(environ, reason)
            inbox = getattr(self.runtime, "tenant_tradingview_alert_inbox", None)
            connection_id = path[len(tv_alert_prefix):-len(tv_alert_suffix)].strip("/")
            if context is None or inbox is None:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": "identidade ou inbox TradingView indisponível", "execution_authorized": False}, request_id)
            try:
                query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
                limit = int(query.get("limit", ["50"])[0])
                events = inbox.list_events(context, connection_id, limit=limit)
            except (ValueError, TypeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.OK, {"events": events, "read_only": True, "execution_authorized": False}, request_id)

        if method == "GET" and path == "/api/market-data/connections":
            try:
                context = _tenant_context_for_request(environ, reason)
            except Exception:
                context = None
            registry = getattr(self.runtime, "tenant_market_data_sessions", None)
            if context is None or registry is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável ou registro de sessões indisponível", "execution_authorized": False},
                    request_id,
                )
            try:
                accounts = registry.status(context)
            except PermissionError:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável inválida", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "connections": accounts,
                    "count": len(accounts),
                    "execution_authorized": False,
                },
                request_id,
            )

        if method == "POST" and path == "/api/market-data/connections":
            try:
                context = _tenant_context_for_request(environ, reason)
            except Exception:
                context = None
            service = getattr(self.runtime, "tenant_provider_connection_service", None)
            if context is None or service is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "identidade confiável ou cofre de credenciais do servidor indisponível", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                allowed = {"provider_id", "account_alias", "credential_ref"}
                if set(payload) - allowed or not allowed.issubset(payload):
                    raise ValueError("envie somente provider_id, account_alias e credential_ref; segredos não são aceitos pela API")
                result = service.connect(
                    context,
                    provider_id=payload["provider_id"],
                    account_alias=payload["account_alias"],
                    credential_ref=payload["credential_ref"],
                )
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "não foi possível verificar a conexão com o provedor", "execution_authorized": False},
                    request_id,
                )
            return _json_response(start_response, HTTPStatus.CREATED, result, request_id)

        if (
            method == "POST"
            and path.startswith("/api/market-data/connections/")
            and path.endswith("/reconnect")
        ):
            prefix = "/api/market-data/connections/"
            connection_id = path[len(prefix):-len("/reconnect")].strip("/")
            if len(connection_id) != 32 or any(
                char not in "0123456789abcdef" for char in connection_id
            ):
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": "connection_id inválido", "execution_authorized": False},
                    request_id,
                )
            try:
                context = _tenant_context_for_request(environ, reason)
            except Exception:
                context = None
            service = getattr(self.runtime, "tenant_provider_connection_service", None)
            if context is None or service is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "identidade confiável ou serviço de reconexão indisponível", "execution_authorized": False},
                    request_id,
                )
            try:
                result = service.reconnect_saved(context, connection_id=connection_id)
            except PermissionError as exc:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": str(exc), "execution_authorized": False}, request_id,
                )
            except (ValueError, TypeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False}, request_id,
                )
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "não foi possível revalidar a conexão com o provedor", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {**result, "execution_authorized": False}, request_id,
            )

        if method == "DELETE" and path.startswith("/api/market-data/connections/"):
            connection_id = path[len("/api/market-data/connections/"):].strip("/")
            if "/" not in connection_id and connection_id:
                try:
                    context = _tenant_context_for_request(environ, reason)
                except Exception:
                    context = None
                service = getattr(self.runtime, "tenant_provider_connection_service", None)
                if context is None or service is None:
                    return _json_response(
                        start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "identidade confiável ou serviço de conexões indisponível", "execution_authorized": False},
                        request_id,
                    )
                try:
                    token_vault = getattr(self.runtime, "tenant_mt5_relay_token_vault", None)
                    if token_vault is not None:
                        token_vault.revoke(context, connection_id)
                    tv_vault = getattr(self.runtime, "tenant_tradingview_webhook_vault", None)
                    if tv_vault is not None:
                        tv_vault.revoke(context, connection_id)
                    ctrader_vault = getattr(self.runtime, "tenant_ctrader_token_vault", None)
                    if ctrader_vault is not None:
                        ctrader_vault.revoke(context, connection_id)
                    result = service.disconnect(context, connection_id=connection_id)
                except (ValueError, TypeError) as exc:
                    return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
                except Exception:
                    return _json_response(
                        start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "não foi possível encerrar a conexão", "execution_authorized": False},
                        request_id,
                    )
                return _json_response(start_response, HTTPStatus.OK, result, request_id)

        if method == "GET" and path == "/api/market-data/providers":
            # User-owned connections are always resolved from trusted tenant
            # scope. Host-global adapters are reported separately to local
            # operators and are never presented as a remote user's accounts.
            context = _tenant_context_for_request(environ, reason)
            connection_registry = getattr(self.runtime, "tenant_provider_connections", None)
            if context is None or connection_registry is None:
                payload = {
                    "status": "USER_SCOPED_PROVIDER_CONNECTIONS_NOT_CONFIGURED",
                    "connections": [],
                    "count": 0,
                    "execution_authorized": False,
                }
            else:
                connections = connection_registry.list_connections(context)
                session_registry = getattr(self.runtime, "tenant_market_data_sessions", None)
                payload = {
                    "status": "AVAILABLE" if connections else "NO_VERIFIED_CONNECTIONS",
                    "connections": connections,
                    "adapter_sessions": (
                        session_registry.status(context)
                        if session_registry is not None else []
                    ),
                    "timeframe_monitor": (
                        self.runtime.tenant_market_monitor.status(context)
                        if getattr(self.runtime, "tenant_market_monitor", None) is not None
                        else {"worker_running": False, "enabled": 0, "total": 0}
                    ),
                    "oauth_token_refresh": (
                        self.runtime.tenant_oauth_refresh_worker.owner_status(context)
                        if getattr(self.runtime, "tenant_oauth_refresh_worker", None) is not None
                        else {
                            "configured": False,
                            "registered": False,
                            "running": False,
                            "state": "NOT_CONFIGURED",
                            "execution_authorized": False,
                        }
                    ),
                    "connection_onboarding": {
                        "connect_enabled": bool(
                            getattr(self.runtime, "tenant_provider_connection_service", None)
                            and self.runtime.tenant_provider_connection_service.secret_resolver is not None
                            and self.runtime.tenant_provider_connection_service.adapter_factories
                        ),
                        "disconnect_enabled": getattr(
                            self.runtime, "tenant_provider_connection_service", None
                        ) is not None,
                        "credential_values_accepted": False,
                    },
                    "count": len(connections),
                    "scope": "TENANT_AND_SUBJECT" if reason == "trusted_identity" else "LOCAL_SINGLE_USER",
                    "execution_authorized": False,
                }
            if reason == "local":
                registry = getattr(self.runtime, "market_data_registry", None)
                payload["configured_data_sources"] = (
                    registry.status(probe_account_mode=False)
                    if registry is not None else {"selected_provider": None, "providers": [], "count": 0}
                )
                payload["providers"] = payload["configured_data_sources"].get("providers", [])
                payload["selected_provider"] = payload["configured_data_sources"].get("selected_provider")
            return _json_response(start_response, HTTPStatus.OK, payload, request_id)

        if method == "GET" and path == "/api/bridge/mt5/status":
            relay = getattr(self.runtime, "mt5_relay_store", None)
            payload = (
                relay.status()
                if relay is not None
                else {"connected": False, "status": "NOT_CONFIGURED", "execution_authorized": False}
            )
            if reason == "trusted_identity":
                # Do not expose global relay source IDs, candle counts or heartbeat
                # metadata to a tenant. Those details belong to local operations.
                payload = {
                    "configured": relay is not None,
                    "status": "STATUS_AVAILABLE_TO_LOCAL_OPERATOR",
                    "scope": "INFRASTRUCTURE_ONLY",
                    "read_only": True,
                    "execution_authorized": False,
                }
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

        if method == "GET" and path == "/api/backup/status":
            scheduler = getattr(self.runtime, "backup_scheduler", None)
            payload = (
                scheduler.status()
                if scheduler is not None
                else {
                    "provider": "LOCAL_SQLITE_SCHEDULED",
                    "enabled": False,
                    "worker_running": False,
                    "status": "NOT_CONFIGURED",
                    "off_host_replication": "NOT_CONFIGURED",
                    "deployment_continuity": "PROCESS_LIFETIME_ONLY",
                    "execution_authorized": False,
                }
            )
            if reason == "trusted_identity":
                # A tenant must not receive shared backup paths, per-database
                # results, exception details or global backup history.
                payload = {
                    "provider": "LOCAL_SQLITE_SCHEDULED",
                    "enabled": bool(payload.get("enabled", False)),
                    "worker_running": bool(payload.get("worker_running", False)),
                    "status": "STATUS_AVAILABLE_TO_LOCAL_OPERATOR",
                    "off_host_replication": "NOT_CONFIGURED",
                    "deployment_continuity": "PROCESS_LIFETIME_ONLY",
                    "scope": "INFRASTRUCTURE_ONLY",
                    "execution_authorized": False,
                }
            return _json_response(start_response, HTTPStatus.OK, payload, request_id)

        if method == "GET" and path == "/api/readiness":
            # Shared runtime readiness contains local operational counters and
            # storage details. Remote users receive only a deliberately minimal
            # infrastructure contract; tenant data is exposed through the
            # dedicated tenant-scoped endpoints instead.
            if reason == "trusted_identity":
                architecture = self.runtime.application.architecture()
                return _json_response(
                    start_response, HTTPStatus.OK,
                    {
                        "identity": IdentityPolicy().status(
                            remote_identity_middleware_configured=True
                        ),
                        "architecture": architecture.get("architecture", "UNKNOWN"),
                        "areas": len(architecture.get("application_areas", [])),
                        "tenant_readiness": "AVAILABLE_ONLY_THROUGH_SCOPED_ENDPOINTS",
                        "notifications": "USE_TENANT_SCOPED_STATUS_ENDPOINT",
                        "market_monitor": "USE_TENANT_SCOPED_STATUS_ENDPOINT",
                        "storage_details": "NOT_EXPOSED_IN_SHARED_READINESS",
                        "deployment": "PROCESS_RUNNING_DEPLOYMENT_NOT_VERIFIED",
                        "deployment_topology": "SINGLE_HOST_SQLITE_MULTI_REPLICA_BLOCKED",
                        "scope": "INFRASTRUCTURE_ONLY",
                        "execution_authorized": False,
                    },
                    request_id,
                )
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
                "backup_scheduler": (
                    self.runtime.backup_scheduler.status()
                    if getattr(self.runtime, "backup_scheduler", None) is not None
                    else {
                        "enabled": False,
                        "status": "NOT_CONFIGURED",
                        "off_host_replication": "NOT_CONFIGURED",
                        "deployment_continuity": "PROCESS_LIFETIME_ONLY",
                    }
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
                "oauth_token_refresh": (
                    self.runtime.tenant_oauth_refresh_worker.status()
                    if getattr(self.runtime, "tenant_oauth_refresh_worker", None) is not None
                    else {
                        "configured": False,
                        "running": False,
                        "registered_owner_count": 0,
                        "state": "NOT_CONFIGURED",
                        "execution_authorized": False,
                    }
                ),
                "provider_recovery": (
                    {
                        "status": (
                            "NO_SAVED_CONNECTIONS" if not self.runtime.provider_recovery_status
                            else "DEGRADED" if any(
                                item.get("status") in {"RECOVERY_NOT_CONFIGURED", "RECONNECT_FAILED"}
                                for item in self.runtime.provider_recovery_status
                            )
                            else "RECOVERY_ATTEMPTED"
                        ),
                        "accounts": [
                            {
                                key: item[key]
                                for key in (
                                    "connection_id", "provider_id", "status",
                                    "adapter_status", "error_class", "execution_authorized",
                                )
                                if key in item
                            }
                            for item in self.runtime.provider_recovery_status
                        ],
                        "execution_authorized": False,
                    }
                    if isinstance(getattr(self.runtime, "provider_recovery_status", None), list)
                    else {
                        "status": "NOT_CONFIGURED",
                        "accounts": [],
                        "execution_authorized": False,
                    }
                ),
                "ctrader_recovery": (
                    {
                        "status": (
                            "NO_SAVED_CONNECTIONS" if not self.runtime.ctrader_recovery_status
                            else "DEGRADED" if any(
                                item.get("status") == "RECONNECT_FAILED"
                                for item in self.runtime.ctrader_recovery_status
                            )
                            else "RECOVERY_ATTEMPTED"
                        ),
                        "accounts": [
                            {
                                key: item[key]
                                for key in (
                                    "connection_id", "provider_id", "status",
                                    "adapter_status", "error_class", "execution_authorized",
                                )
                                if key in item
                            }
                            for item in self.runtime.ctrader_recovery_status
                        ],
                        "execution_authorized": False,
                    }
                    if isinstance(getattr(self.runtime, "ctrader_recovery_status", None), list)
                    else {
                        "status": "NOT_CONFIGURED",
                        "accounts": [],
                        "execution_authorized": False,
                    }
                ),
                "storage_foundation": standalone_storage_status(self.runtime),
                "tenant_state": (
                    self.runtime.tenant_state.readiness()
                    if callable(getattr(getattr(self.runtime, "tenant_state", None), "readiness", None))
                    else {"status": "NOT_CONFIGURED", "production_ready": False}
                ),
                "tenant_decision_memory": (
                    self.runtime.tenant_decision_memory.readiness()
                    if callable(getattr(getattr(self.runtime, "tenant_decision_memory", None), "readiness", None))
                    else {"status": "NOT_CONFIGURED", "production_ready": False}
                ),
                "tenant_fiscal_storage": (
                    self.runtime.tenant_fiscal_store_factory.readiness()
                    if callable(getattr(getattr(self.runtime, "tenant_fiscal_store_factory", None), "readiness", None))
                    else {"status": "NOT_CONFIGURED", "production_ready": False}
                ),
                "deployment": "PROCESS_RUNNING_DEPLOYMENT_NOT_VERIFIED",
                "deployment_topology": getattr(
                    self.runtime, "deployment_topology",
                    {"deployment_topology": "UNKNOWN", "multi_replica_ready": False},
                ),
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
            try:
                tenant_context = _tenant_context_for_request(environ, reason)
            except Exception:
                tenant_context = None
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para consultar o monitor", "execution_authorized": False},
                    request_id,
                )
            payload = (
                monitor.status(tenant_context)
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
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para consultar resultados", "execution_authorized": False},
                    request_id,
                )
            try:
                query = str(environ.get("QUERY_STRING") or "")
                params = dict(
                    item.split("=", 1) for item in query.split("&")
                    if item and "=" in item
                )
                limit = int(params.get("limit", "50"))
                results = monitor.latest_results(limit=limit, context=tenant_context)
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
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para consultar assinaturas", "execution_authorized": False},
                    request_id,
                )
            subscriptions = monitor.subscriptions(tenant_context) if monitor is not None else []
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
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para criar assinatura", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                subscription = monitor.subscribe(
                    symbol=payload.get("symbol"),
                    timeframe=payload.get("timeframe"),
                    context=tenant_context,
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
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para remover assinatura", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                removed = monitor.unsubscribe(
                    symbol=payload.get("symbol"),
                    timeframe=payload.get("timeframe"),
                    context=tenant_context,
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

        if method == "GET" and path == "/api/memory/decisions":
            memory = getattr(self.runtime, "tenant_decision_memory", None)
            if memory is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "memória individual não configurada", "execution_authorized": False},
                    request_id,
                )
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para acessar a memória", "execution_authorized": False},
                    request_id,
                )
            try:
                query = str(environ.get("QUERY_STRING") or "")
                params = dict(
                    item.split("=", 1) for item in query.split("&")
                    if item and "=" in item
                )
                limit = int(params.get("limit", "100"))
                records = memory.load(tenant_context, limit=limit)
            except (ValueError, TypeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "decisions": [item.to_dict() for item in records],
                    "count": len(records),
                    "scope": "TENANT_SCOPED",
                    "execution_authorized": False,
                },
                request_id,
            )

        if method == "GET" and path == "/api/fiscal/summary":
            # The existing fiscal database is bound to one configured local owner.
            # Do not expose it to remote tenants, even when their identity is verified.
            if reason != "local":
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "resumo fiscal remoto indisponível até a persistência fiscal por tenant estar integrada e validada",
                        "state": "FISCAL_REMOTE_STORAGE_NOT_READY",
                        "execution_authorized": False,
                    },
                    request_id,
                )
            tenant_context = _tenant_context_for_request(environ, reason)
            fiscal = getattr(self.runtime, "fiscal_reserve", None)
            owner_id = getattr(self.runtime, "fiscal_owner_id", None)
            if tenant_context is None or fiscal is None or not isinstance(owner_id, str) or not owner_id:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "repositório fiscal local não configurado", "state": "FISCAL_NOT_CONFIGURED", "execution_authorized": False},
                    request_id,
                )
            try:
                params = parse_qs(str(environ.get("QUERY_STRING") or ""), strict_parsing=False)
                raw_limit = params.get("limit", ["100"])[-1]
                raw_offset = params.get("offset", ["0"])[-1]
                limit = int(raw_limit)
                offset = int(raw_offset)
                if isinstance(limit, bool) or not 1 <= limit <= 500:
                    raise ValueError("limit deve estar entre 1 e 500")
                if isinstance(offset, bool) or not 0 <= offset <= 100000:
                    raise ValueError("offset deve estar entre 0 e 100000")
                summary = fiscal.summary(
                    owner_id,
                    history_limit=limit,
                    history_offset=offset,
                )
            except (ValueError, TypeError, OverflowError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "não foi possível consultar o resumo fiscal local", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "summary": summary,
                    "scope": "LOCAL_SINGLE_USER",
                    "tax_assessment": False,
                    "money_movement": False,
                    "execution_authorized": False,
                },
                request_id,
            )

        if path.startswith("/api/market-data/connections/") and path.endswith("/subscriptions"):
            try:
                context = _tenant_context_for_request(environ, reason)
            except Exception:
                context = None
            monitor = getattr(self.runtime, "tenant_market_monitor", None)
            if context is None or monitor is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "monitor de ciclos por conta ou identidade confiável indisponível", "execution_authorized": False},
                    request_id,
                )
            connection_id = path[len("/api/market-data/connections/"):-len("/subscriptions")].strip("/")
            if len(connection_id) != 32 or any(char not in "0123456789abcdef" for char in connection_id):
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "connection_id inválido", "execution_authorized": False}, request_id)
            try:
                if method == "POST":
                    payload = _read_json(environ)
                    item = monitor.subscribe(context, connection_id, payload.get("symbol"), payload.get("timeframe"))
                    return _json_response(start_response, HTTPStatus.CREATED, item, request_id)
                if method == "GET":
                    return _json_response(
                        start_response, HTTPStatus.OK,
                        {"subscriptions": monitor.subscriptions(context, connection_id), "execution_authorized": False},
                        request_id,
                    )
                if method == "DELETE":
                    payload = _read_json(environ)
                    removed = monitor.unsubscribe(context, connection_id, payload.get("symbol"), payload.get("timeframe"))
                    return _json_response(start_response, HTTPStatus.OK, {"unsubscribed": removed, "execution_authorized": False}, request_id)
            except PermissionError as exc:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": str(exc), "execution_authorized": False}, request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)

        if method == "GET" and path == "/api/market-data/timeframe-results":
            try:
                context = _tenant_context_for_request(environ, reason)
            except Exception:
                context = None
            monitor = getattr(self.runtime, "tenant_market_monitor", None)
            if context is None or monitor is None:
                return _json_response(start_response, HTTPStatus.FORBIDDEN, {"error": "identidade ou monitor indisponível", "execution_authorized": False}, request_id)
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            connection_values = query.get("connection_id", [])
            limit_values = query.get("limit", ["50"])
            try:
                connection_id = connection_values[0] if connection_values else None
                limit = int(limit_values[0])
                results = monitor.latest_results(context, connection_id, limit)
            except (ValueError, TypeError) as exc:
                return _json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc), "execution_authorized": False}, request_id)
            return _json_response(start_response, HTTPStatus.OK, {"results": results, "execution_authorized": False}, request_id)

        if method == "POST" and path.startswith("/api/market-data/connections/") and path.endswith("/analysis"):
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para análise por conta", "execution_authorized": False},
                    request_id,
                )
            connection_id = path[len("/api/market-data/connections/"):-len("/analysis")].strip("/")
            if len(connection_id) != 32 or any(char not in "0123456789abcdef" for char in connection_id):
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": "connection_id inválido", "execution_authorized": False},
                    request_id,
                )
            session_registry = getattr(self.runtime, "tenant_market_data_sessions", None)
            session = (
                session_registry.get(tenant_context, connection_id=connection_id)
                if session_registry is not None else None
            )
            if session is None:
                return _json_response(
                    start_response, HTTPStatus.NOT_FOUND,
                    {"error": "conexão sem adaptador ativo para esta identidade", "state": "ADAPTER_NOT_BOUND", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                symbol = payload.get("symbol")
                timeframe = payload.get("timeframe")
                limit = payload.get("limit", 120)
                if not isinstance(symbol, str) or not symbol.strip():
                    raise ValueError("symbol é obrigatório")
                if not isinstance(timeframe, str) or not timeframe.strip():
                    raise ValueError("timeframe é obrigatório")
                if isinstance(limit, bool) or not isinstance(limit, int) or not 3 <= limit <= 1000:
                    raise ValueError("limit deve ser um inteiro de 3 a 1000")
                from integration.standalone_market_analysis import StandaloneMarketAnalysisService
                analyzer = StandaloneMarketAnalysisService(
                    provider=session.adapter,
                    source=session.source,
                    intelligence=self.runtime.intelligence,
                    decision_sink=lambda record, context=None: self.runtime.tenant_decision_memory.save(
                        context or tenant_context, record
                    ),
                )
                result = analyzer.analyze(
                    symbol=symbol.strip(),
                    timeframe=timeframe.strip(),
                    limit=limit,
                    confirmed=False,
                    filters_ok=True,
                    decision_context=tenant_context,
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "análise desta conexão indisponível; nenhuma ordem foi enviada", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    **result,
                    "connection": {
                        "connection_id": session.connection_id,
                        "provider_id": session.provider_id,
                        "source": session.source,
                    },
                    "execution_authorized": False,
                },
                request_id,
            )

        if method == "POST" and path == "/api/analysis/run":
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para executar análise", "execution_authorized": False},
                    request_id,
                )
            analyzer = getattr(self.runtime, "market_analysis_service", None)
            if analyzer is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "provedor de dados/analisador não configurado", "state": "ANALYSIS_NOT_CONFIGURED", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                symbol = payload.get("symbol")
                timeframe = payload.get("timeframe")
                limit = payload.get("limit", 120)
                if not isinstance(symbol, str) or not symbol.strip():
                    raise ValueError("symbol é obrigatório")
                if not isinstance(timeframe, str) or not timeframe.strip():
                    raise ValueError("timeframe é obrigatório")
                if isinstance(limit, bool) or not isinstance(limit, int) or not 3 <= limit <= 1000:
                    raise ValueError("limit deve ser um inteiro de 3 a 1000")
                # Confirmation and filters are server-controlled: this route
                # is analysis-only and cannot accept a client-side approval.
                result = analyzer.analyze(
                    symbol=symbol.strip(),
                    timeframe=timeframe.strip(),
                    limit=limit,
                    confirmed=False,
                    filters_ok=True,
                    decision_context=tenant_context,
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "análise indisponível; nenhuma ordem foi enviada", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "analysis": result,
                    "scope": "TENANT_SCOPED",
                    "execution_authorized": False,
                    "order_submitted": False,
                },
                request_id,
            )

        if method == "GET" and path in {
            "/api/analysis/statistics", "/api/analysis/report"
        }:
            memory = getattr(self.runtime, "tenant_decision_memory", None)
            if memory is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "memória individual não configurada", "execution_authorized": False},
                    request_id,
                )
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para consultar estatísticas e relatórios", "execution_authorized": False},
                    request_id,
                )
            try:
                params = parse_qs(str(environ.get("QUERY_STRING") or ""), strict_parsing=False)
                # The tenant memory retains at most 2,000 records. Loading that
                # complete owner-scoped index is the denominator for all stats.
                records = memory.load(tenant_context, limit=2000)
                if path == "/api/analysis/statistics":
                    payload = summarize_tenant_decisions(records)
                    payload["scope"] = "TENANT_SCOPED"
                    payload["execution_authorized"] = False
                else:
                    raw_limit = params.get("limit", ["1000"])[-1]
                    limit = int(raw_limit)
                    payload = build_tenant_decision_report(records, limit=limit)
                    payload["scope"] = "TENANT_SCOPED"
                    payload["execution_authorized"] = False
            except (ValueError, TypeError, OverflowError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            except Exception:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "não foi possível consultar os dados isolados deste usuário", "execution_authorized": False},
                    request_id,
                )
            return _json_response(start_response, HTTPStatus.OK, payload, request_id)

        if method == "POST" and path == "/api/memory/decisions/outcome":
            memory = getattr(self.runtime, "tenant_decision_memory", None)
            if memory is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "memória individual não configurada", "execution_authorized": False},
                    request_id,
                )
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para acessar a memória", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                record = memory.record_outcome(
                    tenant_context,
                    payload.get("decision_id"),
                    payload.get("outcome"),
                )
            except PermissionError as exc:
                return _json_response(
                    start_response, HTTPStatus.NOT_FOUND,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    "decision": record.to_dict(),
                    "scope": "TENANT_SCOPED",
                    "execution_authorized": False,
                },
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
                tenant_context = _tenant_context_for_request(environ, reason)
                if tenant_context is None:
                    return _json_response(
                        start_response, HTTPStatus.FORBIDDEN,
                        {"error": "identidade individual necessária para acessar notificações", "execution_authorized": False},
                        request_id,
                    )
                if reason == "trusted_identity":
                    tenant_state = getattr(self.runtime, "tenant_state", None)
                    if tenant_state is None:
                        return _json_response(
                            start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "armazenamento individual de notificações não configurado", "execution_authorized": False},
                            request_id,
                        )
                    items = tenant_state.load_notifications(tenant_context)
                    scope = "TENANT_SCOPED"
                else:
                    # The local single-user runtime may continue using its
                    # legacy operational inbox; remote users never see it.
                    include_info = str(params.get("include_info", "false")).lower() in {"1", "true", "yes"}
                    items = self.runtime.ecosystem_service.notification_items(include_info=include_info)
                    # Merge explicitly addressed local-user events with the
                    # legacy local operational inbox. Deduplicate by stable ID.
                    tenant_state = getattr(self.runtime, "tenant_state", None)
                    if tenant_state is not None:
                        scoped_items = tenant_state.load_notifications(tenant_context)
                        seen_ids = {
                            item.get("notification_id")
                            for item in items
                            if isinstance(item, dict) and item.get("notification_id")
                        }
                        items.extend(
                            item for item in scoped_items
                            if item.get("notification_id") not in seen_ids
                        )
                    scope = "LOCAL_SINGLE_USER"
            except (ValueError, TypeError):
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": "limit deve ser um inteiro entre 1 e 200", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {"notifications": items[:limit], "count": min(len(items), limit), "scope": scope, "execution_authorized": False},
                request_id,
            )

        if method == "GET" and path == "/api/notifications/status":
            worker = getattr(self.runtime, "notification_worker", None)
            delivery_worker = worker.status() if worker is not None else {
                "configured": False,
                "running": False,
                "state": "NO_EXTERNAL_SINK_CONFIGURED",
            }
            if worker is None:
                external_delivery = "OUTBOX_ONLY_NO_PROVIDER"
            elif delivery_worker.get("state") == "DEGRADED":
                external_delivery = "WORKER_DEGRADED"
            elif delivery_worker.get("running") is True:
                external_delivery = "WORKER_RUNNING"
            else:
                external_delivery = "WORKER_STOPPED"
            tenant_delivery_worker = getattr(self.runtime, "tenant_notification_worker", None)
            tenant_delivery_status = tenant_delivery_worker.status() if tenant_delivery_worker is not None else {
                "configured": False, "running": False, "state": "NO_TENANT_EXTERNAL_SINK_CONFIGURED",
            }
            if reason == "trusted_identity":
                tenant_context = _tenant_context_for_request(environ, reason)
                tenant_state = getattr(self.runtime, "tenant_state", None)
                if tenant_context is None or tenant_state is None:
                    return _json_response(
                        start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "status individual de notificações não configurado", "execution_authorized": False},
                        request_id,
                    )
                # Never expose another owner's inbox or outbox counts.
                tenant_items = tenant_state.load_notifications(tenant_context)
                tenant_outbox = self.runtime.tenant_notification_dispatcher.outbox
                summary = {
                    "total": len(tenant_items),
                    "scope": "TENANT_SCOPED",
                    "tenant_outbox": tenant_outbox.status_counts(tenant_context),
                    "tenant_delivery_worker": tenant_delivery_status,
                    "tenant_external_delivery": (
                        "WORKER_DEGRADED" if tenant_delivery_status.get("state") == "DEGRADED"
                        else "WORKER_RUNNING" if tenant_delivery_status.get("running") is True
                        else "OUTBOX_ONLY_NO_PROVIDER"
                    ),
                }
            else:
                summary = self.runtime.ecosystem_service.notification_summary()
                summary["scope"] = "LOCAL_SINGLE_USER"
            summary["delivery_worker"] = delivery_worker
            summary["external_delivery"] = external_delivery
            return _json_response(
                start_response, HTTPStatus.OK,
                {**summary, "execution_authorized": False},
                request_id,
            )

        if path.startswith("/api/assistant/conversations"):
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para acessar conversas", "execution_authorized": False},
                    request_id,
                )
            assistant = getattr(self.runtime, "assistant", None)
            if assistant is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "Assistente não configurado", "execution_authorized": False},
                    request_id,
                )
            owner_key = tenant_context.key
            if method == "GET" and path == "/api/assistant/conversations":
                return _json_response(
                    start_response, HTTPStatus.OK,
                    {"conversations": assistant.conversations(owner_key), "scope": "TENANT_SCOPED", "execution_authorized": False},
                    request_id,
                )
            if method == "GET" and path == "/api/assistant/conversations/history":
                params = parse_qs(str(environ.get("QUERY_STRING") or ""), strict_parsing=False)
                conversation_id = params.get("conversation_id", [""])[-1]
                try:
                    history = assistant.history(owner_key, conversation_id)
                except PermissionError:
                    return _json_response(
                        start_response, HTTPStatus.NOT_FOUND,
                        {"error": "conversa não encontrada", "execution_authorized": False},
                        request_id,
                    )
                except ValueError as exc:
                    return _json_response(
                        start_response, HTTPStatus.BAD_REQUEST,
                        {"error": str(exc), "execution_authorized": False},
                        request_id,
                    )
                return _json_response(
                    start_response, HTTPStatus.OK,
                    {"conversation_id": conversation_id, "history": history, "scope": "TENANT_SCOPED", "execution_authorized": False},
                    request_id,
                )
            if method == "DELETE" and path == "/api/assistant/conversations":
                try:
                    payload = _read_json(environ)
                    assistant.delete_conversation(owner_key, payload.get("conversation_id"))
                except PermissionError:
                    return _json_response(
                        start_response, HTTPStatus.NOT_FOUND,
                        {"error": "conversa não encontrada", "execution_authorized": False},
                        request_id,
                    )
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    return _json_response(
                        start_response, HTTPStatus.BAD_REQUEST,
                        {"error": str(exc), "execution_authorized": False},
                        request_id,
                    )
                return _json_response(
                    start_response, HTTPStatus.OK,
                    {"deleted": True, "scope": "TENANT_SCOPED", "execution_authorized": False},
                    request_id,
                )
            return _json_response(
                start_response, HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "método não permitido para conversas", "execution_authorized": False},
                request_id,
            )

        if method == "POST" and path == "/api/assistant/ask":
            tenant_context = _tenant_context_for_request(environ, reason)
            if tenant_context is None:
                return _json_response(
                    start_response, HTTPStatus.FORBIDDEN,
                    {"error": "identidade confiável necessária para usar o Assistente", "execution_authorized": False},
                    request_id,
                )
            assistant = getattr(self.runtime, "assistant", None)
            if assistant is None:
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "Assistente não configurado", "execution_authorized": False},
                    request_id,
                )
            try:
                payload = _read_json(environ)
                if reason == "trusted_identity":
                    # Remote chat may use only the tenant-sharded fiscal
                    # repositories. Never fall back to the local owner's data.
                    fiscal_factory = getattr(
                        self.runtime, "tenant_fiscal_store_factory", None
                    )
                    tenant_ask = getattr(assistant, "ask_tenant", None)
                    if fiscal_factory is None or not callable(tenant_ask):
                        return _json_response(
                            start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                            {
                                "error": "Assistente fiscal individual não configurado",
                                "state": "FISCAL_TENANT_ISOLATION_REQUIRED",
                                "execution_authorized": False,
                            },
                            request_id,
                        )
                    result = tenant_ask(
                        tenant_context=tenant_context,
                        fiscal_store_factory=fiscal_factory,
                        message=payload.get("message"),
                        cid=payload.get("conversation_id"),
                    )
                else:
                    result = assistant.ask(
                        identity=tenant_context.key,
                        message=payload.get("message"),
                        fiscal_owner_id=self.runtime.fiscal_owner_id,
                        cid=payload.get("conversation_id"),
                    )
            except PermissionError:
                return _json_response(
                    start_response, HTTPStatus.NOT_FOUND,
                    {"error": "conversa não encontrada", "execution_authorized": False},
                    request_id,
                )
            except ValueError as exc:
                return _json_response(
                    start_response, HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "execution_authorized": False},
                    request_id,
                )
            except Exception as exc:
                # Never echo provider, fiscal repository or credential details.
                response = {
                    "error": "Assistente indisponível no momento; nenhuma ação foi executada.",
                    "execution_authorized": False,
                }
                if getattr(exc, "conversation_id", None):
                    response["conversation_id"] = exc.conversation_id
                return _json_response(
                    start_response, HTTPStatus.SERVICE_UNAVAILABLE, response, request_id
                )
            return _json_response(
                start_response, HTTPStatus.OK,
                {
                    **result,
                    "scope": (
                        "TENANT_AND_SUBJECT"
                        if reason == "trusted_identity"
                        else "LOCAL_SINGLE_USER"
                    ),
                    "execution_authorized": False,
                },
                request_id,
            )

        if method == "GET" and path == "/api/assistant/status":
            readiness = self.runtime.assistant.readiness()
            tenant_context = _tenant_context_for_request(environ, reason)
            readiness = {
                **readiness,
                "conversation_scope": "TENANT_AND_SUBJECT",
                "conversation_identity_required": True,
                "remote_chat": (
                    "TENANT_SCOPED_FISCAL_CONTEXT"
                    if reason == "trusted_identity"
                    else "LOCAL_SINGLE_USER_ONLY"
                ),
                "tenant_context_available": tenant_context is not None,
                "execution_authorized": False,
            }
            return _json_response(
                start_response, HTTPStatus.OK,
                readiness,
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


def _validate_bind_security(host: str) -> None:
    """Prevent accidental public binding without the complete remote auth boundary."""
    import ipaddress

    normalized = host.strip().lower()
    if normalized == "localhost":
        return
    try:
        is_loopback = ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        is_loopback = False
    if is_loopback:
        return

    remote_required = os.getenv(
        "CONTROLADOR_REMOTE_ACCESS_REQUIRED", ""
    ).strip().lower() in {"1", "true", "yes"}
    middleware_enabled = os.getenv(
        "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE", ""
    ).strip().lower() in {"1", "true", "yes"}
    access_token = os.getenv("CONTROLADOR_STANDALONE_ACCESS_TOKEN", "").strip()
    if not (remote_required and middleware_enabled and access_token):
        raise RuntimeError(
            "bind público bloqueado: configure acesso remoto obrigatório, "
            "token e middleware de identidade confiável"
        )


def main() -> None:
    host = os.getenv("CONTROLADOR_BIND_HOST", "127.0.0.1")
    _validate_bind_security(host)
    runtime = StandaloneRuntime.from_environment()
    application = StandaloneWSGIApplication(runtime)
    port = int(os.getenv("CONTROLADOR_BIND_PORT", "8765"))
    server = make_server(host, port, application, server_class=ThreadingWSGIServer)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.close()


if __name__ == "__main__":
    main()
