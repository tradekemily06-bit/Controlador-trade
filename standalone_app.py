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
    return True, "trusted"

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

        if not SECURITY.allow(environ):
            return _json_response(
                start_response, HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "limite de requisições excedido", "execution_authorized": False},
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

        if method == "GET" and path == "/api/bridge/mt5/status":
            relay = getattr(self.runtime, "mt5_relay_store", None)
            payload = (
                relay.status()
                if relay is not None
                else {"connected": False, "status": "NOT_CONFIGURED", "execution_authorized": False}
            )
            return _json_response(start_response, HTTPStatus.OK, payload, request_id)

        authorized, reason = _authorized(environ)
        if not authorized:
            return _json_response(
                start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": reason, "execution_authorized": False},
                request_id,
            )

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

        if method == "GET" and path == "/api/intelligence/architecture":
            return _json_response(
                start_response, HTTPStatus.OK,
                self.runtime.application.architecture(),
                request_id,
            )

        if method == "GET" and path == "/api/market-data/providers":
            registry = getattr(self.runtime, "market_data_registry", None)
            payload = registry.status() if registry is not None else {"status": "NOT_CONFIGURED", "count": 0}
            return _json_response(
                start_response, HTTPStatus.OK,
                {**payload, "execution_authorized": False},
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
