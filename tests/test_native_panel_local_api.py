from __future__ import annotations

import io
import json

import app as app_module
from assistant.chat_service import AssistantUnavailableError


def _request(path, *, method="GET", payload=None, remote_addr="127.0.0.1", host="localhost:8000"):
    raw = json.dumps(payload or {}).encode("utf-8")
    route, separator, query = path.partition("?")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": route,
        "QUERY_STRING": query if separator else "",
        "REMOTE_ADDR": remote_addr,
        "HTTP_HOST": host,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body)


def _allow_native_local(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost,127.0.0.1,[::1]")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)


def test_native_assistant_status_is_loopback_only(tmp_path, monkeypatch):
    class Assistant:
        def readiness(self):
            return {"available": True}

    _allow_native_local(monkeypatch)
    monkeypatch.setattr(app_module, "ASSISTANT", Assistant())
    monkeypatch.setattr(app_module, "configured_fiscal_owner_id", lambda: "single:native-owner")

    status, payload = _request("/api/assistant/local/status", remote_addr="203.0.113.8")

    assert status.startswith("403")
    assert "error" in payload


def test_native_assistant_chat_requires_explicit_consent_before_provider_or_migration(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssertionError("OpenAI must not be called without explicit consent")

    _allow_native_local(monkeypatch)
    monkeypatch.setattr(app_module, "ASSISTANT", Assistant())
    monkeypatch.setattr(app_module, "configured_fiscal_owner_id", lambda: "single:native-owner")
    monkeypatch.setattr(
        app_module, "migrate_fiscal_schema",
        lambda _path: (_ for _ in ()).throw(AssertionError("migration must not run without consent")),
    )
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request(
        "/api/assistant/local/chat",
        method="POST",
        payload={"message": "Resuma minha reserva", "consent_to_openai": "true"},
    )

    assert status.startswith("400")
    assert "Consentimento explícito" in payload["error"]


def test_native_assistant_chat_uses_canonical_owner_and_persists_conversation(tmp_path, monkeypatch):
    calls = []

    class Assistant:
        def ask(self, identity, message, fiscal_owner_id, conversation_id=None):
            calls.append((identity, message, fiscal_owner_id, conversation_id))
            return {
                "conversation_id": "native-conversation-1",
                "answer": "Resposta somente leitura",
                "read_only": True,
                "execution_allowed": False,
                "may_execute_orders": False,
                "may_enable_real": False,
                "may_move_money": False,
            }

    _allow_native_local(monkeypatch)
    monkeypatch.setattr(app_module, "ASSISTANT", Assistant())
    monkeypatch.setattr(app_module, "configured_fiscal_owner_id", lambda: "single:native-owner")
    monkeypatch.setattr(app_module, "migrate_fiscal_schema", lambda _path: "single:native-owner")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request(
        "/api/assistant/local/chat",
        method="POST",
        payload={
            "message": "Resuma minha reserva",
            "conversation_id": None,
            "consent_to_openai": True,
        },
    )

    assert status.startswith("200")
    assert payload["read_only"] is True
    assert payload["execution_allowed"] is False
    assert calls == [("single:native-owner", "Resuma minha reserva", "single:native-owner", None)]


def test_native_assistant_preserves_conversation_id_when_provider_is_unavailable(tmp_path, monkeypatch):
    class Assistant:
        def ask(self, *args, **kwargs):
            raise AssistantUnavailableError(
                "provider details must not be exposed",
                conversation_id="native-conversation-after-failure",
            )

    _allow_native_local(monkeypatch)
    monkeypatch.setattr(app_module, "ASSISTANT", Assistant())
    monkeypatch.setattr(app_module, "configured_fiscal_owner_id", lambda: "single:native-owner")
    monkeypatch.setattr(app_module, "migrate_fiscal_schema", lambda _path: "single:native-owner")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request(
        "/api/assistant/local/chat",
        method="POST",
        payload={"message": "pergunta", "consent_to_openai": True},
    )

    assert status.startswith("503")
    assert payload["conversation_id"] == "native-conversation-after-failure"
    assert "provider details" not in json.dumps(payload)


def test_native_fiscal_summary_is_loopback_only(tmp_path, monkeypatch):
    _allow_native_local(monkeypatch)
    status, payload = _request(
        "/api/fiscal-reserve/local",
        remote_addr="203.0.113.9",
    )
    assert status.startswith("403")
    assert "error" in payload


def test_native_fiscal_summary_uses_server_owner_and_keeps_foreign_pending_separate(tmp_path, monkeypatch):
    class Fiscal:
        def summary(self, owner_id, history_limit=20, history_offset=0):
            assert owner_id == "single:native-owner"
            assert history_limit == 20
            return {
                "total_reserved_brl": 42.5,
                "categories": {
                    "BR_DAY_TRADE": {"reserve_amount_brl": 42.5, "rate_source": "DEFAULT"},
                    "FOREIGN_FINANCIAL_ASSET": {"rate": 99.0, "reserve_amount_brl": 99.0},
                },
                "history": [{
                    "category": "FOREIGN_FINANCIAL_ASSET",
                    "reserve_rate": 99.0,
                    "reserve_amount_brl": 99.0,
                }],
            }

    class Queue:
        def summary(self, owner_id):
            assert owner_id == "single:native-owner"
            return {
                "total": 3,
                "included_in_totals": False,
                "reserve_calculated": False,
            }

    _allow_native_local(monkeypatch)
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", Fiscal())
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", Queue())
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", Queue())
    monkeypatch.setattr(app_module, "configured_fiscal_owner_id", lambda: "single:native-owner")
    monkeypatch.setattr(app_module, "migrate_fiscal_schema", lambda _path: "single:native-owner")
    monkeypatch.setattr(app_module, "fiscal_classification_catalog", lambda: {})
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")

    status, payload = _request("/api/fiscal-reserve/local")

    assert status.startswith("200")
    assert payload["total_reserved_brl"] == 42.5
    assert payload["foreign_pending"]["total"] == 3
    assert payload["foreign_pending"]["included_in_totals"] is False
    assert payload["categories"]["FOREIGN_FINANCIAL_ASSET"]["reserve_amount_brl"] == 0.0
    assert "rate" not in payload["categories"]["FOREIGN_FINANCIAL_ASSET"]
    assert "reserve_amount_brl" not in payload["history"][0]
    assert payload["domestic_pending"]["total"] == 3
