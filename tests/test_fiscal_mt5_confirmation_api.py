import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import app as app_module
from finance.fiscal_reserve import FiscalReserve


class FakeFiscalAdapter:
    def __init__(self, currency="BRL"):
        self.currency = currency
        self.calls = []

    def read_closed_deal_candidate(self, ticket):
        self.calls.append(ticket)
        if ticket != "7654321":
            raise RuntimeError("ticket não encontrado")
        return {
            "ticket": ticket,
            "symbol": "WINZ26",
            "net_result_account_currency": 250.0,
            "account_currency": self.currency,
            "occurred_at_utc": datetime(2026, 11, 3, 12, tzinfo=timezone.utc).isoformat(),
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
    payload = {"confirmed": True, "ticket": "7654321", "category": "BR_DAY_TRADE",
               "realized_result_brl": 999999, "reference": "CLIENT-FORGED"}
    status, body, adapter = call_confirm(monkeypatch, tmp_path, payload)
    assert status.startswith("201")
    assert body["registered"] is True
    assert body["entry"]["realized_result_brl"] == 250.0
    assert body["entry"]["reference"] == "MT5-DEMO-DEAL:7654321"
    assert body["entry"]["reserve_amount_brl"] == 50.0
    assert adapter.calls == ["7654321"]

    status, body, adapter = call_confirm(monkeypatch, tmp_path, payload)
    assert status.startswith("409")
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
        {"confirmed": True, "ticket": "7654321", "category": "BR_DAY_TRADE"},
        adapter=adapter,
    )
    assert status.startswith("422")
    assert body["registered"] is False
    assert body["classification_status"] == "PENDING_CLASSIFICATION"


def test_mt5_confirmation_requires_explicit_supported_category(monkeypatch, tmp_path):
    status, body, adapter = call_confirm(
        monkeypatch, tmp_path,
        {"confirmed": True, "ticket": "7654321", "category": "FOREIGN_FINANCIAL_ASSET"},
    )
    assert status.startswith("400")
    assert adapter.calls == []
