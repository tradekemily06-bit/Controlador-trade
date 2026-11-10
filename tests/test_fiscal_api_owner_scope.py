import io
import json
import sqlite3

import pytest

import app as app_module
from assistant.conversation_store import AssistantConversationStore
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema
from execution.icmarkets_mt5_demo_adapter import MT5DealNotFoundError


class _ObservedSessionLock:
    def __init__(self):
        self.held = False

    def __enter__(self):
        assert not self.held
        self.held = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.held = False



def _request(path, *, query="", method="GET", payload=None, identity="owner@example.com"):
    raw = json.dumps(payload or {}).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
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


def test_fiscal_api_rejects_malformed_trusted_identity_before_schema_or_store_access(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    def unexpected_schema_access(*args, **kwargs):
        raise AssertionError("fiscal schema/store access must not happen before identity authorization")

    monkeypatch.setattr(app_module, "migrate_fiscal_schema", unexpected_schema_access)

    for malformed_identity in ("x" * 321, "owner@example.com\r\nX-Injected: yes", "owner@example.com\x00", "owner@example.com\x7f"):
        status, body = _request(
            "/api/fiscal-reserve",
            identity=malformed_identity,
        )
        assert status.startswith("401")
        assert "total_reserved_brl" not in body


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
    import execution.mt5_session_lock as mt5_session_lock

    adapter = app_module.SERVICE.mt5_operational_adapter
    session_lock = _ObservedSessionLock()
    monkeypatch.setattr(mt5_session_lock, "MT5_TERMINAL_SESSION_LOCK", session_lock)
    monkeypatch.setattr(adapter, "_session_lock", session_lock)
    original_add = queue.add_realized_result

    def add_while_session_locked(*args, **kwargs):
        assert session_lock.held, "MT5 session lock must cover fiscal persistence"
        return original_add(*args, **kwargs)

    monkeypatch.setattr(queue, "add_realized_result", add_while_session_locked)

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
    assert fiscal_summary["foreign_pending"]["evidence_completeness"] == {
        "total": 1,
        "missing_institution": 1,
        "missing_custody_location": 1,
        "missing_contract_type": 1,
        "missing_core_evidence": 1,
    }
    assert fiscal_summary["foreign_pending"]["included_in_totals"] is False
    assert "PENDING-B-ONLY" not in json.dumps(pending)

    status, conversations = _request(
        "/api/assistant/conversations", query="owner_id=single%3Aother-owner"
    )
    assert status.startswith("200")
    assert len(conversations["conversations"]) == 1
    assert conversations["conversations"][0]["title"] == "conversa do titular"
    assert "conversa de outra identidade" not in json.dumps(conversations)


def test_fiscal_pending_intake_ignores_forged_owner_id_in_request_bodies(tmp_path, monkeypatch):
    database = tmp_path / "forged-owner-body.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    foreign_queue = FiscalPendingQueue(str(database))
    domestic_queue = FiscalDomesticPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", foreign_queue)
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", domestic_queue)

    status, foreign = _request(
        "/api/fiscal-reserve/pending",
        method="POST",
        payload={
            "owner_id": "single:attacker-selected-owner",
            "reference": "OWNER-BODY-FOREIGN-001",
            "original_amount": 50,
            "original_currency": "USD",
            "instrument": "ETF",
            "jurisdiction": "PENDING_REVIEW",
            "occurred_on": "2026-11-05",
            "tax_residency_at_event": "NOT_INFORMED",
            "income_nature": "INVESTMENT_INCOME",
            "event_type": "ACQUISITION",
            "fx_conversion_method": "NOT_CONVERTED",
        },
    )
    assert status.startswith("201")
    assert foreign_queue.list_pending(owner_id)["total"] == 1
    assert foreign_queue.list_pending("single:attacker-selected-owner")["total"] == 0

    status, domestic = _request(
        "/api/fiscal-reserve/domestic-pending",
        method="POST",
        payload={
            "owner_id": "single:attacker-selected-owner",
            "reference": "OWNER-BODY-DOMESTIC-001",
            "category_candidate": "BR_FII_FIAGRO",
            "instrument": "FII",
            "market_scope": "B3",
            "occurred_on": "2026-11-05",
            "realized_result_brl": 75,
        },
    )
    assert status.startswith("201")
    assert domestic_queue.list_pending(owner_id)["total"] == 1
    assert domestic_queue.list_pending("single:attacker-selected-owner")["total"] == 0


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
            "institution": "Broker API",
            "custody_location": "Custódia estrangeira",
            "contract_type": "ETF à vista",
            "acquisition_cost": 120.0,
            "transaction_fees": 2.5,
            "foreign_tax_paid": 1.25,
        },
    )
    assert status.startswith("201")
    pending_id = created["pending"]["pending_id"]
    assert created["pending"]["status"] == "PENDING_CLASSIFICATION"
    assert created["pending"]["institution"] == "Broker API"
    assert created["pending"]["custody_location"] == "Custódia estrangeira"
    assert created["pending"]["contract_type"] == "ETF à vista"
    assert created["pending"]["acquisition_cost"] == 120.0
    assert created["pending"]["transaction_fees"] == 2.5
    assert created["pending"]["foreign_tax_paid"] == 1.25
    assert created["reserve_calculated"] is False

    status, realized = _request(
        "/api/fiscal-reserve/pending-result",
        method="POST",
        payload={
            "owner_id": "single:attacker-selected-owner",
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
            "institution": "Broker EU",
            "custody_location": "Custódia na UE",
            "contract_type": "Derivativo",
            "acquisition_cost": 500.0,
            "transaction_fees": 3.0,
            "foreign_tax_paid": 0.0,
        },
    )
    assert status.startswith("201")
    assert realized["pending"]["institution"] == "Broker EU"
    assert realized["pending"]["custody_location"] == "Custódia na UE"
    assert realized["pending"]["contract_type"] == "Derivativo"
    assert realized["pending"]["acquisition_cost"] == 500.0
    assert realized["pending"]["transaction_fees"] == 3.0
    assert realized["pending"]["foreign_tax_paid"] == 0.0
    assert realized["pending"]["original_result"] == -37.25
    assert realized["pending"]["status"] == "PENDING_CLASSIFICATION"
    assert realized["classification_status"] == "PENDING_CLASSIFICATION"
    assert realized["reserve_calculated"] is False

    review_payload = {
        "owner_id": "single:attacker-selected-owner",
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
    assert queue.list_pending("single:attacker-selected-owner")["total"] == 0
    with pytest.raises(ValueError, match="pendência não encontrada"):
        queue.list_reviews("single:attacker-selected-owner", pending_id)
    assert len(queue.list_reviews(owner_id, pending_id)) == 1
    assert listing["total"] == 2
    assert {item["reference"] for item in listing["items"]} == {
        "FOREIGN-API-ASSET-001",
        "FOREIGN-API-RESULT-001",
    }
    assert all(item["status"] == "PENDING_CLASSIFICATION" for item in listing["items"])




def test_mt5_pending_result_ignores_forged_owner_id_and_uses_authenticated_owner(
    tmp_path, monkeypatch
):
    database = tmp_path / "mt5-pending-owner.sqlite3"
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
    import execution.mt5_session_lock as mt5_session_lock

    adapter = app_module.SERVICE.mt5_operational_adapter
    session_lock = _ObservedSessionLock()
    monkeypatch.setattr(mt5_session_lock, "MT5_TERMINAL_SESSION_LOCK", session_lock)
    monkeypatch.setattr(adapter, "_session_lock", session_lock)

    candidate = {
        "account_currency": "USD",
        "account_fingerprint": "a" * 32,
        "occurred_at_utc": "2026-11-05T15:30:00+00:00",
        "opened_at_utc": "2026-11-05T14:30:00+00:00",
        "position_id": "POSITION-001",
        "profit": 25.0,
        "commission": -1.0,
        "swap": 0.0,
        "fee": 0.0,
        "net_result_account_currency": 24.0,
        "symbol": "EURUSD",
        "deal_count": 2,
        "closing_deal_count": 1,
    }
    def read_candidate_while_session_locked(ticket):
        assert session_lock.held, "MT5 history read must use the same session lock"
        return candidate if ticket == "TICKET-001" else None

    monkeypatch.setattr(
        app_module.SERVICE.mt5_operational_adapter,
        "read_closed_deal_candidate",
        read_candidate_while_session_locked,
    )

    status, response = _request(
        "/api/fiscal-reserve/mt5-pending-result",
        method="POST",
        payload={
            "confirmed": True,
            "ticket": "TICKET-001",
            "owner_id": "single:attacker-selected-owner",
        },
    )

    assert status.startswith("201")
    assert response["registered"] is True
    assert response["reserve_calculated"] is False
    assert queue.list_pending(owner_id)["total"] == 1
    assert queue.list_pending("single:attacker-selected-owner")["total"] == 0


def test_mt5_brazil_confirmation_is_owner_scoped_and_ticket_deduplicated(
    tmp_path, monkeypatch
):
    database = tmp_path / "mt5-domestic-confirm-owner.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    queue = FiscalDomesticPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", queue)
    import execution.mt5_session_lock as mt5_session_lock

    adapter = app_module.SERVICE.mt5_operational_adapter
    session_lock = _ObservedSessionLock()
    monkeypatch.setattr(mt5_session_lock, "MT5_TERMINAL_SESSION_LOCK", session_lock)
    monkeypatch.setattr(adapter, "_session_lock", session_lock)
    original_add = queue.add

    def add_while_session_locked(*args, **kwargs):
        assert session_lock.held, "MT5 session lock must cover fiscal persistence"
        return original_add(*args, **kwargs)

    monkeypatch.setattr(queue, "add", add_while_session_locked)

    candidate = {
        "account_currency": "BRL",
        "account_fingerprint": "b" * 32,
        "occurred_at_utc": "2026-11-05T15:30:00+00:00",
        "opened_at_utc": "2026-11-05T14:30:00+00:00",
        "position_id": "POSITION-BR-001",
        "profit": 25.0,
        "commission": -1.0,
        "swap": 0.0,
        "fee": 0.0,
        "net_result_account_currency": 24.0,
        "symbol": "WINZ26",
        "deal_count": 2,
        "closing_deal_count": 1,
    }
    def read_candidate_while_session_locked(ticket):
        assert session_lock.held, "MT5 history read must use the same session lock"
        return candidate if ticket == "TICKET-BR-001" else None

    monkeypatch.setattr(
        app_module.SERVICE.mt5_operational_adapter,
        "read_closed_deal_candidate",
        read_candidate_while_session_locked,
    )

    payload = {
        "confirmed": True,
        "ticket": "TICKET-BR-001",
        "category": "BR_DAY_TRADE",
        "market_scope": "BR_ELIGIBLE_MARKET",
        "owner_id": "single:attacker-selected-owner",
    }
    status, response = _request(
        "/api/fiscal-reserve/mt5-confirm", method="POST", payload=payload
    )
    assert status.startswith("201")
    assert response["registered"] is True
    assert response["reserve_calculated"] is False
    assert response["included_in_totals"] is False
    assert queue.list_pending(owner_id)["total"] == 1
    assert queue.list_pending("single:attacker-selected-owner")["total"] == 0

    duplicate_status, duplicate = _request(
        "/api/fiscal-reserve/mt5-confirm", method="POST", payload=payload
    )
    assert duplicate_status.startswith("409")
    assert duplicate["registered"] is False
    assert queue.list_pending(owner_id)["total"] == 1

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


def test_domestic_pending_api_list_summary_and_reviews_are_owner_scoped(
    tmp_path, monkeypatch
):
    database = tmp_path / "domestic-owner-api.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    queue = FiscalDomesticPendingQueue(str(database))
    own_item = queue.add(owner_id, {
        "reference": "BR-OWNER-ONLY",
        "category_candidate": "BR_FII_FIAGRO",
        "instrument": "FII",
        "market_scope": "B3",
        "occurred_on": "2026-11-04",
        "realized_result_brl": 120.0,
    })
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", queue)

    status, listing = _request(
        "/api/fiscal-reserve/domestic-pending",
        query="owner_id=single%3Aother-owner",
    )
    assert status.startswith("200")
    assert listing["total"] == 1
    assert [item["reference"] for item in listing["items"]] == ["BR-OWNER-ONLY"]
    assert "BR-OTHER-OWNER-ONLY" not in json.dumps(listing)

    status, summary = _request(
        "/api/fiscal-reserve/domestic-pending/summary",
        query="owner_id=single%3Aother-owner",
    )
    assert status.startswith("200")
    assert summary["total"] == 1
    assert summary["included_in_totals"] is False
    assert summary["reserve_calculated"] is False

    status, own_reviews = _request(
        f"/api/fiscal-reserve/domestic-pending/{own_item['pending_id']}/reviews",
        query="owner_id=single%3Aother-owner",
    )
    assert status.startswith("200")
    assert own_reviews["reviews"] == []

    status, other_reviews = _request(
        "/api/fiscal-reserve/domestic-pending/nonexistent-foreign-id/reviews",
        query="owner_id=single%3Aother-owner",
    )
    assert status.startswith("200")
    assert other_reviews["reviews"] == []

def test_mt5_fiscal_confirmation_rejects_missing_ticket_and_unresolved_history_candidate(
    tmp_path, monkeypatch
):
    database = tmp_path / "mt5-unresolved-ticket.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    foreign_queue = FiscalPendingQueue(str(database))
    domestic_queue = FiscalDomesticPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", foreign_queue)
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", domestic_queue)

    def no_history_candidate(ticket):
        assert ticket == "TICKET-NOT-FOUND"
        return None

    monkeypatch.setattr(
        app_module.SERVICE.mt5_operational_adapter,
        "read_closed_deal_candidate",
        no_history_candidate,
    )

    foreign_base = {"confirmed": True}
    domestic_base = {
        "confirmed": True,
        "category": "BR_DAY_TRADE",
        "market_scope": "BR_ELIGIBLE_MARKET",
    }
    for path, base in (
        ("/api/fiscal-reserve/mt5-pending-result", foreign_base),
        ("/api/fiscal-reserve/mt5-confirm", domestic_base),
    ):
        missing_status, missing = _request(
            path, method="POST", payload=base
        )
        assert missing_status.startswith("400")
        assert missing.get("registered") is not True

        unresolved_status, unresolved = _request(
            path,
            method="POST",
            payload={**base, "ticket": "TICKET-NOT-FOUND"},
        )
        assert unresolved_status.startswith("422")
        assert unresolved["registered"] is False
        assert unresolved["reserve_calculated"] is False
        assert unresolved["execution_allowed"] is False

    assert foreign_queue.list_pending(owner_id)["total"] == 0
    assert domestic_queue.list_pending(owner_id)["total"] == 0


def test_mt5_missing_deal_exception_returns_422_without_registering_fiscal_records(
    tmp_path, monkeypatch
):
    database = tmp_path / "mt5-missing-deal.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    foreign_queue = FiscalPendingQueue(str(database))
    domestic_queue = FiscalDomesticPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", foreign_queue)
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", domestic_queue)

    def missing_deal(ticket):
        assert ticket == "987654321"
        raise MT5DealNotFoundError("closed deal absent")

    monkeypatch.setattr(
        app_module.SERVICE.mt5_operational_adapter,
        "read_closed_deal_candidate",
        missing_deal,
    )

    cases = (
        ("/api/fiscal-reserve/mt5-pending-result", {"confirmed": True}),
        ("/api/fiscal-reserve/mt5-confirm", {
            "confirmed": True,
            "category": "BR_DAY_TRADE",
            "market_scope": "BR_ELIGIBLE_MARKET",
        }),
    )
    for path, base_payload in cases:
        status, body = _request(
            path,
            method="POST",
            payload={**base_payload, "ticket": "987654321"},
        )
        assert status.startswith("422")
        assert body["registered"] is False
        assert body["reserve_calculated"] is False
        assert body["execution_allowed"] is False

    assert foreign_queue.list_pending(owner_id)["total"] == 0
    assert domestic_queue.list_pending(owner_id)["total"] == 0


def test_foreign_pending_api_returns_conflict_for_duplicate_asset_and_realized_references(
    tmp_path, monkeypatch
):
    database = tmp_path / "foreign-pending-duplicate-api.sqlite3"
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

    asset = {
        "reference": "FOREIGN-DUPLICATE-ASSET-API-001",
        "original_amount": 100.0,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-04",
    }
    status, created = _request(
        "/api/fiscal-reserve/pending", method="POST", payload=asset
    )
    assert status.startswith("201")
    assert created["reserve_calculated"] is False

    duplicate_status, duplicate = _request(
        "/api/fiscal-reserve/pending", method="POST", payload=asset
    )
    assert duplicate_status.startswith("409")
    assert "referência" in duplicate["error"].lower()

    realized = {
        "reference": "FOREIGN-DUPLICATE-RESULT-API-001",
        "original_result": -25.0,
        "original_currency": "EUR",
        "instrument": "ETF",
        "jurisdiction": "EU",
        "occurred_on": "2026-11-04",
    }
    status, created_result = _request(
        "/api/fiscal-reserve/pending-result", method="POST", payload=realized
    )
    assert status.startswith("201")
    assert created_result["reserve_calculated"] is False

    duplicate_result_status, duplicate_result = _request(
        "/api/fiscal-reserve/pending-result",
        method="POST",
        payload=realized,
    )
    assert duplicate_result_status.startswith("409")
    assert "referência" in duplicate_result["error"].lower()
    assert queue.list_pending(owner_id)["total"] == 2
    assert queue.summary(owner_id)["total"] == 2


def test_fiscal_post_with_wrong_trusted_identity_is_forbidden_before_schema_access(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    def unexpected_schema_access(*args, **kwargs):
        raise AssertionError("unauthorized identity must be rejected before fiscal schema access")

    monkeypatch.setattr(app_module, "migrate_fiscal_schema", unexpected_schema_access)
    status, response = _request(
        "/api/fiscal-reserve/domestic-pending",
        method="POST",
        identity="attacker@example.com",
        payload={
            "owner_id": "single:attacker-selected-owner",
            "reference": "BR-UNAUTHORIZED-001",
            "instrument": "ETF",
            "occurred_on": "2026-11-06",
        },
    )

    assert status.startswith("403")
    assert "pending" not in json.dumps(response).lower()
    assert "attacker-selected-owner" not in json.dumps(response)


def test_fiscal_api_migration_failure_does_not_expose_internal_exception_details(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    def broken_migration(*args, **kwargs):
        raise RuntimeError("SECRET_DB_PATH=/srv/private/fiscal.sqlite3; SQL=SELECT * FROM private_table")

    monkeypatch.setattr(app_module, "migrate_fiscal_schema", broken_migration)
    status, response = _request("/api/fiscal-reserve/domestic-pending")

    assert status.startswith("503")
    assert response["error"] == "Reserva Fiscal indisponível até validar a identidade proprietária e a migração."
    assert "detail" not in response
    assert "SECRET_DB_PATH" not in json.dumps(response)
    assert "private_table" not in json.dumps(response)


def test_permission_error_response_does_not_expose_internal_exception_details(
    monkeypatch,
):
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    private_detail = "C:\\private\\runtime\\fiscal.sqlite3 SELECT secret_column"

    def raise_private_permission_error(*args, **kwargs):
        raise PermissionError(private_detail)

    monkeypatch.setattr(app_module, "_file_response", raise_private_permission_error)

    status, body = _request("/")

    assert status.startswith("403")
    assert body["error"] == "Ação não autorizada."
    assert private_detail not in json.dumps(body)
    assert "fiscal.sqlite3" not in json.dumps(body)
    assert "secret_column" not in json.dumps(body)


def test_fiscal_history_api_rejects_offsets_outside_supported_range(tmp_path, monkeypatch):
    database = tmp_path / "fiscal-history-offset.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    owner_id = migrate_fiscal_schema(str(database))
    reserve = FiscalReserve(str(database))
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", reserve)

    for offset in ("-1", "1000000001", "9223372036854775808"):
        status, response = _request("/api/fiscal-reserve", query=f"limit=50&offset={offset}")
        assert status.startswith("400")
        assert response["error"] == "Entrada inválida"
        assert "history" not in response
    assert reserve.summary(owner_id)["history_page"]["total"] == 0



def test_fiscal_summary_returns_sanitized_unavailable_when_sqlite_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", tmp_path / "fiscal.sqlite3")
    monkeypatch.setattr(app_module, "migrate_fiscal_schema", lambda _path: "single:canonical-owner")

    class BrokenFiscalReserve:
        def summary(self, *args, **kwargs):
            raise sqlite3.OperationalError("database is locked: /private/runtime/fiscal.sqlite3")

    monkeypatch.setattr(app_module, "FISCAL_RESERVE", BrokenFiscalReserve())

    status, payload = _request("/api/fiscal-reserve")

    assert status.startswith("503")
    assert payload["error"] == (
        "Persistência temporariamente indisponível; nenhuma alteração foi confirmada."
    )
    assert "database is locked" not in json.dumps(payload)
    assert str(tmp_path) not in json.dumps(payload)



def test_fiscal_api_to_assistant_context_flow_preserves_evidence_and_privacy(tmp_path, monkeypatch):
    from assistant.read_only_context import collect_read_only_context

    database = tmp_path / "fiscal-assistant-end-to-end.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "fiscal-assistant-e2e-owner")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner = migrate_fiscal_schema(str(database))
    reserve = FiscalReserve(str(database))
    queue = FiscalPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", reserve)
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", queue)

    status, created = _request(
        "/api/fiscal-reserve/pending",
        method="POST",
        payload={
            "reference": "PRIVATE-E2E-REFERENCE",
            "original_amount": 250,
            "original_currency": "USD",
            "instrument": "ETF",
            "jurisdiction": "US",
            "occurred_on": "2026-11-06",
            "institution": "PRIVATE-E2E-BROKER",
            "custody_location": "Custódia estrangeira",
            "contract_type": "ETF à vista",
            "acquisition_cost": 200,
            "transaction_fees": 2,
            "foreign_tax_paid": 0,
            "notes": "PRIVATE-E2E-NOTE",
        },
        identity="fiscal-assistant-e2e-owner",
    )
    assert status.startswith("201")
    assert created["pending"]["status"] == "PENDING_CLASSIFICATION"
    assert created["reserve_calculated"] is False

    status, fiscal = _request(
        "/api/fiscal-reserve", identity="fiscal-assistant-e2e-owner"
    )
    assert status.startswith("200")
    assert fiscal["foreign_pending"]["evidence_completeness"]["missing_core_evidence"] == 0

    class Service:
        def system_status(self):
            return {"mode": "SIMULACAO", "health": "OK", "components": {}}

        def risk_status(self):
            return {"allowed": False}

        def operational_observability(self):
            return {"execution": {"allowed": False, "mode": "DEMO"}}

        def statistics(self):
            return {"total_decisions": 0}

        def memory_view(self, limit=5):
            return []

    class Reserve:
        def summary(self, requested_owner):
            assert requested_owner == owner
            return {
                "as_of": "2026-11-06",
                "total_reserved_brl": 0.0,
                "categories": {},
                "periods": {},
            }

    context = collect_read_only_context(Service(), Reserve(), owner, queue)
    pending = context["fiscal_reserve"]["foreign_pending"]

    assert pending["total"] == 1
    assert pending["evidence_completeness"]["missing_core_evidence"] == 0
    assert pending["included_in_totals"] is False
    assert pending["reserve_calculated"] is False
    serialized_context = json.dumps(context, ensure_ascii=False)
    for private_value in (
        "PRIVATE-E2E-REFERENCE",
        "PRIVATE-E2E-BROKER",
        "PRIVATE-E2E-NOTE",
    ):
        assert private_value not in serialized_context

    # Compare numeric JSON leaves, not substrings: ISO timestamps may contain
    # digit sequences such as ".250" that are unrelated to private amounts.
    def numeric_leaves(value):
        if isinstance(value, dict):
            for child in value.values():
                yield from numeric_leaves(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from numeric_leaves(child)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            yield value

    assert 250 not in list(numeric_leaves(context))
    assert 200 not in list(numeric_leaves(context))
    assert "original_amount" not in pending
    assert "original_result" not in pending


def test_assistant_chat_without_explicit_consent_fails_before_fiscal_context_or_provider_access(
    tmp_path, monkeypatch
):
    database = tmp_path / "assistant-consent.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    def forbidden_context_access(*args, **kwargs):
        raise AssertionError("fiscal context must not be assembled without explicit consent")

    monkeypatch.setattr(app_module, "migrate_fiscal_schema", forbidden_context_access)

    status, body = _request(
        "/api/assistant/chat",
        method="POST",
        payload={
            "message": "Resuma minha conta",
            "consent_to_openai": False,
        },
    )

    assert status.startswith("400")
    assert body["error"] == "Consentimento explícito para envio do contexto à OpenAI é obrigatório."
    assert not database.exists()


def test_assistant_conversation_store_blocks_cross_owner_history_append_and_delete(tmp_path):
    store = AssistantConversationStore(tmp_path / "assistant-owner-isolation.sqlite3")
    owner_a = "owner-a@example.com"
    owner_b = "owner-b@example.com"

    conversation_id = store.append(owner_a, None, "user", "mensagem privada do titular A")
    store.append(owner_a, conversation_id, "assistant", "resposta privada do titular A")

    with pytest.raises(PermissionError, match="conversa não encontrada"):
        store.history(owner_b, conversation_id)

    with pytest.raises(PermissionError, match="conversa não encontrada"):
        store.append(owner_b, conversation_id, "user", "tentativa de inserir mensagem")

    with pytest.raises(PermissionError, match="conversa não encontrada"):
        store.delete(owner_b, conversation_id)

    owner_history = store.history(owner_a, conversation_id)
    assert [message["role"] for message in owner_history] == ["user", "assistant"]
    assert [message["content"] for message in owner_history] == [
        "mensagem privada do titular A",
        "resposta privada do titular A",
    ]
    assert len(store.list(owner_a)) == 1
    assert store.list(owner_b) == []


def test_assistant_conversation_owner_identity_is_case_insensitive(tmp_path):
    store = AssistantConversationStore(tmp_path / "assistant-owner-normalization.sqlite3")
    conversation_id = store.append(
        "Owner@Example.com", None, "user", "mensagem do mesmo titular"
    )

    assert store.history("owner@example.com", conversation_id)[0]["content"] == "mensagem do mesmo titular"


def test_assistant_history_and_delete_routes_hide_foreign_conversation_ids(tmp_path, monkeypatch):
    database = tmp_path / "assistant-route-owner-isolation.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Auth-User")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    store = AssistantConversationStore(tmp_path / "assistant-route-owner-isolation.sqlite3")
    owner_conversation = store.append(owner_id, None, "user", "histórico privado do titular")
    foreign_conversation = store.append(
        "single:other-owner", None, "user", "histórico de outro titular"
    )

    class Assistant:
        def conversations(self, identity):
            return store.list(identity)

        def history(self, identity, conversation_id):
            return store.history(identity, conversation_id)

        def delete_conversation(self, identity, conversation_id):
            return store.delete(identity, conversation_id)

    monkeypatch.setattr(app_module, "ASSISTANT", Assistant())

    status, body = _request(
        "/api/assistant/history",
        query=f"conversation_id={foreign_conversation}",
    )
    assert status.startswith("404")
    assert body["error"] == "conversa não encontrada"

    status, body = _request(
        "/api/assistant/conversations",
        method="DELETE",
        query=f"conversation_id={foreign_conversation}",
    )
    assert status.startswith("404")
    assert body["error"] == "conversa não encontrada"

    assert store.history(owner_id, owner_conversation)[0]["content"] == (
        "histórico privado do titular"
    )
    assert store.history("single:other-owner", foreign_conversation)[0]["content"] == (
        "histórico de outro titular"
    )

    status, body = _request(
        "/api/assistant/history",
        query=f"conversation_id={owner_conversation}",
    )
    assert status.startswith("200")
    assert body["messages"][0]["content"] == "histórico privado do titular"

    status, body = _request(
        "/api/assistant/conversations",
        method="DELETE",
        query=f"conversation_id={owner_conversation}",
    )
    assert status.startswith("200")
    assert body["deleted"] is True
    assert store.list(owner_id) == []
    assert store.list("single:other-owner") == [
        store.list("single:other-owner")[0]
    ]
