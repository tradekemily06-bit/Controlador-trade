import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import app as app_module
from finance.fiscal_reserve import FiscalReserve


class FakeFiscalAdapter:
    def __init__(self, currency="BRL", result=250.0):
        self.currency = currency
        self.result = result
        self.calls = []

    def read_closed_deal_candidate(self, ticket):
        self.calls.append(ticket)
        if ticket != "7654321":
            raise RuntimeError("ticket não encontrado")
        return {
            "ticket": ticket,
            "symbol": "WINZ26",
            "net_result_account_currency": self.result,
            "account_currency": self.currency,
            "opened_at_utc": datetime(2026, 11, 3, 11, tzinfo=timezone.utc).isoformat(),
            "occurred_at_utc": datetime(2026, 11, 3, 12, tzinfo=timezone.utc).isoformat(),
            "account_fingerprint": "a" * 32,
            "profit": self.result,
            "commission": 0.0,
            "swap": 0.0,
            "fee": 0.0,
            "position_id": "12345",
            "auto_registered": False,
        }


def call_confirm(monkeypatch, tmp_path, payload, adapter=None):
    database = tmp_path / "fiscal.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", FiscalReserve(str(database)))
    fake = adapter or FakeFiscalAdapter()
    monkeypatch.setattr(
        app_module,
        "SERVICE",
        SimpleNamespace(mt5_operational_adapter=fake),
    )
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    raw = json.dumps(payload).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/fiscal-reserve/mt5-confirm",
        "QUERY_STRING": "",
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "localhost:8000",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = headers

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body), fake


def test_mt5_confirmation_revalidates_and_registers_once(monkeypatch, tmp_path):
    payload = {"confirmed": True, "ticket": "7654321", "category": "BR_DAY_TRADE", "market_scope": "BR_ELIGIBLE_MARKET",
               "realized_result_brl": 999999, "reference": "CLIENT-FORGED"}
    status, body, adapter = call_confirm(monkeypatch, tmp_path, payload)
    assert status.startswith("201")
    assert body["registered"] is True
    assert body["entry"]["realized_result_brl"] == 250.0
    assert body["entry"]["reference"] == "MT5-DEMO:" + ("a" * 32) + ":7654321"
    assert body["entry"]["reserve_amount_brl"] == 50.0
    assert adapter.calls == ["7654321"]

    status, body, adapter = call_confirm(monkeypatch, tmp_path, payload)
    assert status.startswith("409")
    assert body["registered"] is False


def test_mt5_confirmation_requires_account_fingerprint_for_safe_deduplication(monkeypatch, tmp_path):
    class MissingFingerprintAdapter(FakeFiscalAdapter):
        def read_closed_deal_candidate(self, ticket):
            result = super().read_closed_deal_candidate(ticket)
            result["account_fingerprint"] = None
            return result

    status, body, _ = call_confirm(
        monkeypatch, tmp_path,
        {"confirmed": True, "ticket": "7654321", "category": "BR_DAY_TRADE", "market_scope": "BR_ELIGIBLE_MARKET"},
        adapter=MissingFingerprintAdapter(),
    )
    assert status.startswith("503")
    assert body["registered"] is False


def test_mt5_confirmation_rejects_without_explicit_user_confirmation(monkeypatch, tmp_path):
    status, body, adapter = call_confirm(
        monkeypatch, tmp_path,
        {"confirmed": False, "ticket": "7654321", "category": "BR_DAY_TRADE"},
    )
    assert status.startswith("400")
    assert adapter.calls == []


def test_mt5_confirmation_keeps_non_brl_account_unregistered(monkeypatch, tmp_path):
    adapter = FakeFiscalAdapter(currency="USD")
    status, body, _ = call_confirm(
        monkeypatch, tmp_path,
        {"confirmed": True, "ticket": "7654321", "category": "BR_DAY_TRADE", "market_scope": "BR_ELIGIBLE_MARKET"},
        adapter=adapter,
    )
    assert status.startswith("422")
    assert body["registered"] is False
    assert body["classification_status"] == "PENDING_CLASSIFICATION"


def test_mt5_confirmation_requires_explicit_brazilian_market_scope(monkeypatch, tmp_path):
    status, body, adapter = call_confirm(
        monkeypatch, tmp_path,
        {"confirmed": True, "ticket": "7654321", "category": "BR_DAY_TRADE"},
    )
    assert status.startswith("400")
    assert adapter.calls == []


def test_mt5_confirmation_requires_explicit_supported_category(monkeypatch, tmp_path):
    status, body, adapter = call_confirm(
        monkeypatch, tmp_path,
        {"confirmed": True, "ticket": "7654321", "category": "FOREIGN_FINANCIAL_ASSET"},
    )
    assert status.startswith("400")
    assert adapter.calls == []


def call_pending_result(monkeypatch, tmp_path, payload, adapter=None):
    from finance.fiscal_pending_queue import FiscalPendingQueue
    from finance.fiscal_schema import migrate_fiscal_schema

    database = tmp_path / "fiscal-pending.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    migrate_fiscal_schema(str(database))
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", FiscalReserve(str(database)))
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", FiscalPendingQueue(str(database)))
    fake = adapter or FakeFiscalAdapter(currency="USD")
    monkeypatch.setattr(app_module, "SERVICE", SimpleNamespace(mt5_operational_adapter=fake))
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    raw = json.dumps(payload).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/fiscal-reserve/mt5-pending-result",
        "QUERY_STRING": "",
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "localhost:8000",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = headers

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body), fake


def test_mt5_foreign_result_is_imported_as_pending_with_private_dedupe_key(monkeypatch, tmp_path):
    status, body, adapter = call_pending_result(
        monkeypatch, tmp_path, {"confirmed": True, "ticket": "7654321"}
    )
    assert status.startswith("201")
    assert body["registered"] is True
    pending = body["pending"]
    assert pending["original_result"] == 250.0
    assert pending["original_currency"] == "USD"
    assert pending["record_kind"] == "REALIZED_RESULT"
    assert pending["status"] == "PENDING_CLASSIFICATION"
    assert pending["reference"] == "MT5-DEMO:" + ("a" * 32) + ":7654321"
    assert body["reserve_calculated"] is False
    assert body["execution_allowed"] is False
    assert adapter.calls == ["7654321"]
    status, duplicate, _ = call_pending_result(
        monkeypatch, tmp_path, {"confirmed": True, "ticket": "7654321"}
    )
    assert status.startswith("409")
    assert duplicate["registered"] is False


def test_mt5_foreign_pending_import_rejects_missing_confirmation_and_brl(monkeypatch, tmp_path):
    status, _, adapter = call_pending_result(
        monkeypatch, tmp_path, {"confirmed": False, "ticket": "7654321"}
    )
    assert status.startswith("400")
    assert adapter.calls == []

    status, body, _ = call_pending_result(
        monkeypatch, tmp_path, {"confirmed": True, "ticket": "7654321"},
        adapter=FakeFiscalAdapter(currency="BRL"),
    )
    assert status.startswith("422")
    assert body["registered"] is False
    assert body["reserve_calculated"] is False


def test_mt5_foreign_pending_import_rejects_missing_account_fingerprint(monkeypatch, tmp_path):
    adapter = FakeFiscalAdapter(currency="USD")
    original = adapter.read_closed_deal_candidate

    def candidate(ticket):
        result = original(ticket)
        result["account_fingerprint"] = None
        return result

    adapter.read_closed_deal_candidate = candidate
    status, body, _ = call_pending_result(
        monkeypatch, tmp_path, {"confirmed": True, "ticket": "7654321"}, adapter=adapter
    )
    assert status.startswith("503")
    assert body["registered"] is False


def test_mt5_foreign_loss_keeps_negative_sign_in_original_currency(monkeypatch, tmp_path):
    status, body, _ = call_pending_result(
        monkeypatch, tmp_path,
        {"confirmed": True, "ticket": "7654321"},
        adapter=FakeFiscalAdapter(currency="EUR", result=-42.75),
    )
    assert status.startswith("201")
    assert body["pending"]["original_result"] == -42.75
    assert body["pending"]["original_amount"] == 42.75
    assert body["pending"]["original_currency"] == "EUR"
    assert body["pending"]["status"] == "PENDING_CLASSIFICATION"
    assert body["reserve_calculated"] is False



def test_mt5_confirmation_rejects_position_opened_on_a_different_local_day(monkeypatch, tmp_path):
    class OvernightPositionAdapter(FakeFiscalAdapter):
        def read_closed_deal_candidate(self, ticket):
            result = super().read_closed_deal_candidate(ticket)
            result["opened_at_utc"] = datetime(2026, 11, 2, 12, tzinfo=timezone.utc).isoformat()
            return result

    status, body, adapter = call_confirm(
        monkeypatch,
        tmp_path,
        {"confirmed": True, "ticket": "7654321", "category": "BR_DAY_TRADE", "market_scope": "BR_ELIGIBLE_MARKET"},
        adapter=OvernightPositionAdapter(),
    )
    assert status.startswith("422")
    assert body["registered"] is False
    assert body["classification_status"] == "PENDING_CLASSIFICATION"
    assert body["opened_on"] == "2026-11-02"
    assert body["closed_on"] == "2026-11-03"
    assert adapter.calls == ["7654321"]
