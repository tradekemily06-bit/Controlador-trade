import io
import json

import app as app_module
from assistant.conversation_store import AssistantConversationStore
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema


def _request(path, *, query="", method="GET", payload=None):
    raw = json.dumps(payload or {}).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "REMOTE_ADDR": "203.0.113.10",
        "HTTP_HOST": "control.example",
        "HTTP_X_AUTH_USER": "owner@example.com",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
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
    queue.add(owner_id, {
        "reference": "PENDING-A-ONLY",
        "original_amount": 25,
        "original_currency": "USD",
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
    fiscal_summary_status, fiscal_summary = _request("/api/fiscal-reserve")
    assert fiscal_summary_status.startswith("200")
    assert fiscal_summary["foreign_pending"]["total"] == 1
    assert fiscal_summary["foreign_pending"]["currencies"] == ["USD"]
    assert fiscal_summary["foreign_pending"]["included_in_totals"] is False
    assert "PENDING-B-ONLY" not in json.dumps(pending)

    status, conversations = _request(
        "/api/assistant/conversations", query="owner_id=single%3Aother-owner"
    )
    assert status.startswith("200")
    assert len(conversations["conversations"]) == 1
    assert conversations["conversations"][0]["title"] == "conversa do titular"
    assert "conversa de outra identidade" not in json.dumps(conversations)


def test_assistant_readiness_api_requires_trusted_identity_and_returns_no_secret(tmp_path, monkeypatch):
    from types import SimpleNamespace

    database = tmp_path / "assistant-status.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "ASSISTANT", SimpleNamespace(readiness=lambda: {
        "available": True,
        "provider": "OpenAI API",
        "model": "gpt-4o-mini",
        "connection_tested": False,
        "read_only": True,
        "may_execute_orders": False,
        "may_enable_real": False,
        "may_move_money": False,
    }))

    status, body = _request("/api/assistant/status")

    assert status.startswith("200")
    assert body["available"] is True
    assert body["connection_tested"] is False
    assert body["read_only"] is True
    assert body["may_execute_orders"] is False
    assert body["may_enable_real"] is False
    assert body["may_move_money"] is False
    assert "OPENAI_API_KEY" not in json.dumps(body)



def test_foreign_pending_api_intake_results_and_reviews_stay_owner_scoped_and_unbooked(
    tmp_path, monkeypatch
):
    database = tmp_path / "foreign-pending-api.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    queue = FiscalPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", queue)

    status, created = _request(
        "/api/fiscal-reserve/pending",
        method="POST",
        payload={
            "reference": "FOREIGN-API-ASSET-001",
            "original_amount": 125.5,
            "original_currency": "USD",
            "instrument": "ETF",
            "jurisdiction": "PENDING_REVIEW",
            "occurred_on": "2026-11-04",
            "tax_residency_at_event": "NOT_INFORMED",
            "income_nature": "INVESTMENT_INCOME",
            "event_type": "ACQUISITION",
            "fx_conversion_method": "NOT_CONVERTED",
        },
    )
    assert status.startswith("201")
    pending_id = created["pending"]["pending_id"]
    assert created["pending"]["status"] == "PENDING_CLASSIFICATION"
    assert created["reserve_calculated"] is False

    status, realized = _request(
        "/api/fiscal-reserve/pending-result",
        method="POST",
        payload={
            "reference": "FOREIGN-API-RESULT-001",
            "original_result": -37.25,
            "original_currency": "EUR",
            "instrument": "ETF",
            "jurisdiction": "PENDING_REVIEW",
            "occurred_on": "2026-11-04",
            "tax_residency_at_event": "NOT_INFORMED",
            "income_nature": "TRADING_RESULT",
            "event_type": "DISPOSAL",
            "fx_conversion_method": "NOT_CONVERTED",
        },
    )
    assert status.startswith("201")
    assert realized["pending"]["original_result"] == -37.25
    assert realized["pending"]["status"] == "PENDING_CLASSIFICATION"
    assert realized["classification_status"] == "PENDING_CLASSIFICATION"
    assert realized["reserve_calculated"] is False

    review_payload = {
        "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
        "confirmed_jurisdiction": "PENDING_REVIEW",
        "reviewer_name": "Profissional declarado",
        "reviewer_role": "contador",
        "professional_registration": "REGISTRO-DECLARADO",
        "evidence_reference": "DOC-FOREIGN-API-001",
        "reviewed_on": "2026-11-04",
        "review_notes": "Identidade e registro não verificados pelo sistema.",
    }
    status, reviewed = _request(
        f"/api/fiscal-reserve/pending/{pending_id}/reviews",
        method="POST",
        payload=review_payload,
    )
    assert status.startswith("201")
    assert reviewed["review"]["reviewer_identity_status"] == "DECLARED_NOT_VERIFIED"
    assert reviewed["review"]["professional_registration_verified"] is False
    assert reviewed["reserve_calculated"] is False

    status, reviews = _request(
        f"/api/fiscal-reserve/pending/{pending_id}/reviews",
        query="owner_id=forged-owner",
    )
    assert status.startswith("200")
    assert len(reviews["reviews"]) == 1
    assert reviews["reviews"][0]["evidence_reference"] == "DOC-FOREIGN-API-001"
    assert reviews["status_unchanged"] == "PENDING_CLASSIFICATION"
    assert reviews["reserve_calculated"] is False

    invalid_review_payload = {**review_payload, "candidate_classification": "BR_DAY_TRADE"}
    status, invalid_review = _request(
        f"/api/fiscal-reserve/pending/{pending_id}/reviews",
        method="POST",
        payload=invalid_review_payload,
    )
    assert status.startswith("400")
    assert invalid_review["error"] == "Entrada inválida"

    listing = queue.list_pending(owner_id)
    assert listing["total"] == 2
    assert {item["reference"] for item in listing["items"]} == {
        "FOREIGN-API-ASSET-001",
        "FOREIGN-API-RESULT-001",
    }
    assert all(item["status"] == "PENDING_CLASSIFICATION" for item in listing["items"])



def test_domestic_pending_api_rejects_foreign_review_category(tmp_path, monkeypatch):
    database = tmp_path / "domestic-review-api.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    queue = FiscalDomesticPendingQueue(str(database))
    pending = queue.add(owner_id, {
        "reference": "BR-API-REVIEW-001",
        "category_candidate": "BR_COMMON_EXCHANGE",
        "instrument": "ETF",
        "market_scope": "B3",
        "occurred_on": "2026-11-04",
        "realized_result_brl": -25.0,
    })
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", queue)

    status, response = _request(
        f"/api/fiscal-reserve/domestic-pending/{pending['pending_id']}/reviews",
        method="POST",
        payload={
            "candidate_classification": "FOREIGN_CRYPTO",
            "confirmed_jurisdiction": "Exterior",
            "reviewer_name": "Profissional declarado",
            "reviewer_role": "contador",
            "professional_registration": "CRC-DECLARADO",
            "evidence_reference": "DOC-BR-API-001",
            "reviewed_on": "2026-11-04",
        },
    )

    assert status.startswith("400")
    assert response["error"] == "Entrada inválida"
    assert queue.list_pending(owner_id)["items"][0]["status"] == "PENDING_CLASSIFICATION"
    assert queue.list_reviews(owner_id, pending["pending_id"]) == []
