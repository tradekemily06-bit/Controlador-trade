import io
import json

import app as app_module
from assistant.conversation_store import AssistantConversationStore
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema


def _request(path, *, query="", method="GET"):
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "REMOTE_ADDR": "203.0.113.10",
        "HTTP_HOST": "control.example",
        "HTTP_X_AUTH_USER": "owner@example.com",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body)


def test_fiscal_and_assistant_read_routes_ignore_forged_owner_parameters(
    tmp_path, monkeypatch
):
    database = tmp_path / "fiscal.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    reserve = FiscalReserve(str(database))
    queue = FiscalPendingQueue(str(database))
    reserve.record_realized_result(owner_id, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 100,
        "reference": "OWNER-A-ONLY",
        "occurred_on": "2026-11-03",
    })
    reserve.update_rate("single:other-owner", "BR_DAY_TRADE", 20)
    reserve.record_realized_result("single:other-owner", {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 900,
        "reference": "OWNER-B-ONLY",
        "occurred_on": "2026-11-03",
    })
    queue.add(owner_id, {
        "reference": "PENDING-A-ONLY",
        "original_amount": 25,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "PENDING_REVIEW",
        "occurred_on": "2026-11-03",
    })
    queue.add("single:other-owner", {
        "reference": "PENDING-B-ONLY",
        "original_amount": 75,
        "original_currency": "EUR",
        "instrument": "ETF",
        "jurisdiction": "PENDING_REVIEW",
        "occurred_on": "2026-11-03",
    })
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", reserve)
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", queue)

    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")
    store.append(owner_id, None, "user", "conversa do titular")
    store.append("single:other-owner", None, "user", "conversa de outra identidade")

    class Assistant:
        def conversations(self, identity):
            return store.list(identity)

    monkeypatch.setattr(app_module, "ASSISTANT", Assistant())

    status, fiscal = _request("/api/fiscal-reserve", query="owner_id=single%3Aother-owner")
    assert status.startswith("200")
    assert fiscal["total_reserved_brl"] == 20
    assert [item["reference"] for item in fiscal["history"]] == ["OWNER-A-ONLY"]
    assert "OWNER-B-ONLY" not in json.dumps(fiscal)

    status, pending = _request(
        "/api/fiscal-reserve/pending", query="owner_id=single%3Aother-owner"
    )
    assert status.startswith("200")
    assert pending["total"] == 1
    assert [item["reference"] for item in pending["items"]] == ["PENDING-A-ONLY"]
    assert "PENDING-B-ONLY" not in json.dumps(pending)

    status, conversations = _request(
        "/api/assistant/conversations", query="owner_id=single%3Aother-owner"
    )
    assert status.startswith("200")
    assert len(conversations["conversations"]) == 1
    assert conversations["conversations"][0]["title"] == "conversa do titular"
    assert "conversa de outra identidade" not in json.dumps(conversations)
