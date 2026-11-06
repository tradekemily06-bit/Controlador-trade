import io
import json

import app as app_module
from assistant.chat_service import AssistantUnavailableError


def _request(path, *, method="GET", payload=None, identity="owner@example.com"):
    raw = json.dumps(payload or {}).encode("utf-8")
    route, separator, query = path.partition("?")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": route,
        "QUERY_STRING": query if separator else "",
        "REMOTE_ADDR": "203.0.113.10",
        "HTTP_HOST": "control.example",
        "HTTP_X_AUTH_USER": identity,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body)


def _configure(monkeypatch, assistant):
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "migrate_fiscal_schema", lambda _path: "single:canonical-owner")
    monkeypatch.setattr(app_module, "ASSISTANT", assistant)


def test_chat_api_uses_authenticated_canonical_owner_not_client_owner(tmp_path, monkeypatch):
    calls = []

    class Assistant:
        def ask(self, identity, message, fiscal_owner_id, conversation_id=None):
            calls.append((identity, message, fiscal_owner_id, conversation_id))
            return {
                "conversation_id": "conversation-1",
                "answer": "Resposta simulada",
                "read_only": True,
                "execution_allowed": False,
                "may_execute_orders": False,
                "may_enable_real": False,
                "may_move_money": False,
            }

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request(
        "/api/assistant/chat",
        method="POST",
        payload={
            "message": "Resuma minha Reserva Fiscal",
            "conversation_id": None,
            "owner_id": "single:forged-owner",
            "consent_to_openai": True,
        },
    )

    assert status.startswith("200")
    assert payload["read_only"] is True
    assert payload["execution_allowed"] is False
    assert calls == [(
        "single:canonical-owner",
        "Resuma minha Reserva Fiscal",
        "single:canonical-owner",
        None,
    )]


def test_chat_api_returns_sanitized_provider_unavailable_response(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssistantUnavailableError(
                "Não foi possível obter resposta agora; sua mensagem ficou no histórico."
            )

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request(
        "/api/assistant/chat",
        method="POST",
        payload={"message": "Resuma minha Reserva Fiscal", "consent_to_openai": True},
    )

    assert status.startswith("503")
    assert "histórico" in payload["error"]
    assert "OPENAI_API_KEY" not in json.dumps(payload)


def test_chat_api_rejects_missing_trusted_identity_before_assistant_call(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssertionError("Assistente não pode ser chamado sem identidade confiável")

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request(
        "/api/assistant/chat",
        method="POST",
        payload={"message": "Resuma minha Reserva Fiscal"},
        identity="",
    )

    assert status.startswith("401")
    assert payload["error"] == "trusted identity is required"


def test_chat_api_rejects_missing_or_false_openai_consent_before_assistant_call(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssertionError("Assistente não pode ser chamado sem consentimento explícito")

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    for payload in (
        {"message": "Explique minha Reserva Fiscal"},
        {"message": "Explique minha Reserva Fiscal", "consent_to_openai": False},
        {"message": "Explique minha Reserva Fiscal", "consent_to_openai": "true"},
        {"message": "Explique minha Reserva Fiscal", "consent_to_openai": 1},
        {"message": "Explique minha Reserva Fiscal", "consent_to_openai": None},
    ):
        status, response = _request(
            "/api/assistant/chat",
            method="POST",
            payload=payload,
        )
        assert status.startswith("400")
        assert response["error"] == (
            "Consentimento explícito para envio do contexto à OpenAI é obrigatório."
        )


def test_every_assistant_endpoint_requires_trusted_identity_before_access(tmp_path, monkeypatch):
    class Assistant:
        def readiness(self):
            raise AssertionError("status must not be exposed without identity")

        def conversations(self, identity):
            raise AssertionError("conversation list must not be exposed without identity")

        def history(self, identity, conversation_id):
            raise AssertionError("history must not be exposed without identity")

        def delete_conversation(self, identity, conversation_id):
            raise AssertionError("delete must not run without identity")

        def ask(self, *args, **kwargs):
            raise AssertionError("provider must not be called without identity")

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    for path, method, payload in (
        ("/api/assistant/status", "GET", None),
        ("/api/assistant/conversations", "GET", None),
        ("/api/assistant/history?conversation_id=conversation-1", "GET", None),
        ("/api/assistant/conversations?conversation_id=conversation-1", "DELETE", None),
        ("/api/assistant/chat", "POST", {"message": "pergunta", "consent_to_openai": True}),
    ):
        status, response = _request(
            path,
            method=method,
            payload=payload,
            identity="",
        )
        assert status.startswith("401")
        assert response["error"] == "trusted identity is required"
