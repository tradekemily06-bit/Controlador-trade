import io
import json

import app as app_module
from assistant.conversation_store import AssistantConversationStore


OWNER = "single:canonical-owner"


def _request(path, *, method="GET", identity="owner@example.com"):
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "REMOTE_ADDR": "203.0.113.10",
        "HTTP_HOST": "control.example",
        "HTTP_X_AUTH_USER": identity,
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body)


class AssistantHistoryFacade:
    def __init__(self, store):
        self.store = store

    def conversations(self, identity):
        return self.store.list(identity)

    def history(self, identity, conversation_id):
        return self.store.history(identity, conversation_id)

    def delete_conversation(self, identity, conversation_id):
        return self.store.delete(identity, conversation_id)


def _configure(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "migrate_fiscal_schema", lambda _path: OWNER)
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")
    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")
    monkeypatch.setattr(app_module, "ASSISTANT", AssistantHistoryFacade(store))
    return store


def test_history_api_lists_and_loads_only_authenticated_owner_conversations(tmp_path, monkeypatch):
    store = _configure(tmp_path, monkeypatch)
    own_id = store.append(OWNER, None, "user", "Minha conversa")
    store.append(OWNER, own_id, "assistant", "Resposta")
    other_id = store.append("single:other-owner", None, "user", "Conversa alheia")

    status, listing = _request("/api/assistant/conversations")
    assert status.startswith("200")
    assert [item["conversation_id"] for item in listing["conversations"]] == [own_id]

    status, history = _request(
        "/api/assistant/history",
        identity="owner@example.com",
    )
    # The endpoint requires a conversation_id; missing identifiers fail closed.
    assert status.startswith("400")
    assert "conversation_id" in history["error"]

    environ_query = "conversation_id=" + own_id
    original = app_module.parse_qs
    monkeypatch.setattr(app_module, "parse_qs", lambda value, **kwargs: original(environ_query, **kwargs))
    status, history = _request("/api/assistant/history")
    assert status.startswith("200")
    assert [item["content"] for item in history["messages"]] == ["Minha conversa", "Resposta"]

    monkeypatch.setattr(app_module, "parse_qs", lambda value, **kwargs: original("conversation_id=" + other_id, **kwargs))
    status, history = _request("/api/assistant/history")
    assert status.startswith("404")
    assert history["error"] == "conversa não encontrada"


def test_history_api_delete_is_owner_scoped_and_removes_messages(tmp_path, monkeypatch):
    store = _configure(tmp_path, monkeypatch)
    own_id = store.append(OWNER, None, "user", "Apagar esta conversa")
    store.append(OWNER, own_id, "assistant", "Resposta")
    other_id = store.append("single:other-owner", None, "user", "Não apagar")

    original = app_module.parse_qs
    monkeypatch.setattr(app_module, "parse_qs", lambda value, **kwargs: original("conversation_id=" + other_id, **kwargs))
    status, payload = _request("/api/assistant/conversations", method="DELETE")
    assert status.startswith("404")
    assert payload["error"] == "conversa não encontrada"
    assert store.history("single:other-owner", other_id)[0]["content"] == "Não apagar"

    monkeypatch.setattr(app_module, "parse_qs", lambda value, **kwargs: original("conversation_id=" + own_id, **kwargs))
    status, payload = _request("/api/assistant/conversations", method="DELETE")
    assert status.startswith("200")
    assert payload["deleted"] is True
    assert store.list(OWNER) == []
    assert store.list("single:other-owner")[0]["conversation_id"] == other_id
