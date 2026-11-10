import io
import json
import sqlite3

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
    monkeypatch.setattr(app_module, "configured_fiscal_owner_id", lambda: "single:canonical-owner")
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
                "Não foi possível obter resposta agora; sua mensagem ficou no histórico.",
                conversation_id="conversation-after-provider-failure",
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
    assert payload["conversation_id"] == "conversation-after-provider-failure"
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


def test_all_assistant_routes_reject_malformed_identity_before_store_access(tmp_path, monkeypatch):
    class Assistant:
        def readiness(self):
            raise AssertionError("status não pode ser acessado com identidade inválida")

        def conversations(self, identity):
            raise AssertionError("conversas não podem ser acessadas com identidade inválida")

        def history(self, identity, conversation_id):
            raise AssertionError("histórico não pode ser acessado com identidade inválida")

        def delete_conversation(self, identity, conversation_id):
            raise AssertionError("conversa não pode ser excluída com identidade inválida")

        def ask(self, *args, **kwargs):
            raise AssertionError("provedor não pode ser chamado com identidade inválida")

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
            identity="x" * 321,
        )
        assert status.startswith(("401", "403"))
        assert "error" in response


def test_chat_api_rejects_malformed_trusted_identity_before_assistant_call(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssertionError("Assistente não pode ser chamado com identidade malformada")

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    for identity in (
        "x" * 321,
        "owner@example.com\r\nX-Admin: true",
        "owner@example.com\x00",
        "owner@example.com\x7f",
    ):
        status, response = _request(
            "/api/assistant/chat",
            method="POST",
            payload={"message": "pergunta", "consent_to_openai": True},
            identity=identity,
        )
        assert status.startswith("401")
        assert response["error"] == "trusted identity is invalid"


def test_chat_api_rejects_missing_or_false_openai_consent_before_assistant_call(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssertionError("Assistente não pode ser chamado sem consentimento explícito")

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    def unexpected_fiscal_migration(_path):
        raise AssertionError("sem consentimento, nenhuma migração ou leitura fiscal deve ocorrer")

    monkeypatch.setattr(app_module, "migrate_fiscal_schema", unexpected_fiscal_migration)

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

def test_assistant_history_routes_do_not_migrate_or_access_fiscal_schema(tmp_path, monkeypatch):
    calls = []

    class Assistant:
        def readiness(self):
            return {"ready": True}

        def conversations(self, identity):
            calls.append(("conversations", identity))
            return []

        def history(self, identity, conversation_id):
            calls.append(("history", identity, conversation_id))
            return []

        def delete_conversation(self, identity, conversation_id):
            calls.append(("delete", identity, conversation_id))

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(
        app_module,
        "migrate_fiscal_schema",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("rotas de histórico não devem migrar o banco fiscal")
        ),
    )

    for path, method in (
        ("/api/assistant/status", "GET"),
        ("/api/assistant/conversations", "GET"),
        ("/api/assistant/history?conversation_id=conversation-1", "GET"),
        ("/api/assistant/conversations?conversation_id=conversation-1", "DELETE"),
    ):
        status, _ = _request(path, method=method)
        assert status.startswith("200")

    assert calls == [
        ("conversations", "single:canonical-owner"),
        ("history", "single:canonical-owner", "conversation-1"),
        ("delete", "single:canonical-owner", "conversation-1"),
    ]


def test_notification_recovery_api_requires_authenticated_identity_and_explicit_confirmation(monkeypatch):
    calls = []

    class StateStore:
        def archive_notifications_for_recovery(self, *, confirmed=False):
            calls.append(("archive", confirmed))
            return {"archive_id": "archive-1", "payload_sha256": "a" * 64}

        def inspect_notification_quarantine(self, archive_id):
            calls.append(("inspect", archive_id))
            return {
                "archive_id": archive_id,
                "payload_sha256": "a" * 64,
                "notification_count": 2,
                "notifications": [{"message": "private notification body"}],
                "integrity_verified": True,
                "fully_valid": True,
            }

        def restore_notifications_from_quarantine(self, archive_id, *, confirmed=False):
            calls.append(("restore", archive_id, confirmed))
            return {
                "archive_id": archive_id,
                "restored_count": 2,
                "integrity_verified": True,
                "archive_preserved": True,
            }

    class Service:
        state_store = StateStore()

        def restore_notification_history(self, archive_id, *, confirmed=False):
            calls.append(("runtime_restore", archive_id, confirmed))
            return self.state_store.restore_notifications_from_quarantine(
                archive_id, confirmed=confirmed
            )

    _configure(monkeypatch, object())
    monkeypatch.setattr(app_module, "SERVICE", Service())

    status, payload = _request(
        "/api/notifications/recovery/archive",
        method="POST",
        payload={"confirmed": False},
    )
    assert status.startswith("400")
    assert calls == []

    status, payload = _request(
        "/api/notifications/recovery/archive",
        method="POST",
        payload={"confirmed": True},
    )
    assert status.startswith("201")
    assert payload["archive"]["archive_id"] == "archive-1"
    assert payload["original_preserved"] is True

    status, payload = _request(
        "/api/notifications/recovery/inspect?archive_id=archive-1",
    )
    assert status.startswith("200")
    assert payload["archive"]["fully_valid"] is True
    assert "notifications" not in payload["archive"]
    assert "private notification body" not in json.dumps(payload)

    status, payload = _request(
        "/api/notifications/recovery/restore",
        method="POST",
        payload={"archive_id": "archive-1", "confirmed": True},
    )
    assert status.startswith("200")
    assert payload["restoration"]["archive_preserved"] is True
    assert calls == [
        ("archive", True),
        ("inspect", "archive-1"),
        ("runtime_restore", "archive-1", True),
        ("restore", "archive-1", True),
    ]


def test_notification_recovery_inspection_rejects_missing_trusted_identity(monkeypatch):
    class StateStore:
        def inspect_notification_quarantine(self, archive_id):
            raise AssertionError("quarantine must not be inspected without trusted identity")

    class Service:
        state_store = StateStore()

    _configure(monkeypatch, object())
    monkeypatch.setattr(app_module, "SERVICE", Service())

    status, payload = _request(
        "/api/notifications/recovery/inspect?archive_id=archive-1",
        identity="",
    )
    assert status.startswith("401")
    assert "error" in payload



def test_chat_api_returns_sanitized_unavailable_when_fiscal_sqlite_fails(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssertionError("OpenAI não pode ser chamada quando a persistência fiscal falha")

    _configure(monkeypatch, Assistant())

    def broken_migration(_path):
        raise sqlite3.OperationalError("database is locked: /private/runtime/fiscal.sqlite3")

    monkeypatch.setattr(app_module, "migrate_fiscal_schema", broken_migration)
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request(
        "/api/assistant/chat",
        method="POST",
        payload={"message": "Consulte minha reserva", "consent_to_openai": True},
    )

    assert status.startswith("503")
    assert payload["error"] == (
        "Persistência temporariamente indisponível; nenhuma alteração foi confirmada."
    )
    assert "database is locked" not in json.dumps(payload)
    assert str(tmp_path) not in json.dumps(payload)



def test_assistant_connection_test_is_authenticated_and_sends_no_fiscal_context(monkeypatch):
    calls = []

    class Assistant:
        def test_connection(self):
            calls.append("provider_test")
            return {
                "success": True,
                "connection_tested": True,
                "context_sent": False,
                "history_sent": False,
                "conversation_saved": False,
                "read_only": True,
                "may_execute_orders": False,
                "may_enable_real": False,
                "may_move_money": False,
            }

    _configure(monkeypatch, Assistant())
    monkeypatch.setattr(
        app_module,
        "migrate_fiscal_schema",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("connection test must not read or migrate fiscal data")
        ),
    )

    status, payload = _request(
        "/api/assistant/test-connection",
        method="POST",
        payload={},
    )

    assert status.startswith("200")
    assert payload["connection_tested"] is True
    assert payload["context_sent"] is False
    assert payload["history_sent"] is False
    assert payload["conversation_saved"] is False
    assert calls == ["provider_test"]


def test_assistant_connection_test_rejects_missing_identity_before_provider(monkeypatch):
    class Assistant:
        def test_connection(self):
            raise AssertionError("provider must not be reached without trusted identity")

    _configure(monkeypatch, Assistant())
    status, payload = _request(
        "/api/assistant/test-connection",
        method="POST",
        payload={},
        identity="",
    )

    assert status.startswith("401")
    assert payload["error"] == "trusted identity is required"
