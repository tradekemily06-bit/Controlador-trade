import io
import json

import app as app_module
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema


def _configure(tmp_path, monkeypatch):
    database = tmp_path / "manual-daytrade.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "manual-daytrade-owner")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    reserve = FiscalReserve(str(database))
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", reserve)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    return database, reserve


def _request(payload):
    raw = json.dumps(payload).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/fiscal-reserve/results",
        "QUERY_STRING": "",
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "localhost:8000",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body)


def valid_payload():
    return {
        "realized_result_brl": 250.0,
        "reference": "B3-DAYTRADE-001",
        "occurred_on": "2026-11-04",
        "instrument": "PETR4",
        "institution": "Intermediária declarada",
        "market_label": "B3",
        "market_scope": "BR_ELIGIBLE_MARKET",
        "same_asset": True,
        "same_institution": True,
        "same_day": True,
        "confirmed": True,
        "notes": "Conferir nota de corretagem.",
    }


def test_manual_day_trade_entry_requires_explicit_user_declaration_and_is_only_a_planning_estimate(tmp_path, monkeypatch):
    database, reserve = _configure(tmp_path, monkeypatch)

    payload = valid_payload()\n    payload["notes"] = "E" * 600\n    status, body = _request(payload)

    assert status.startswith("200")
    assert body["classification_status"] == "USER_DECLARED_PLANNING_ONLY"
    assert body["classification_source"] == "USER_DECLARATION"
    assert body["independent_market_eligibility_verified"] is False
    assert body["tax_liability_confirmed"] is False
    assert body["reserve_is_estimate"] is True
    assert body["entry"]["realized_result_brl"] == 250.0
    assert body["entry"]["reserve_amount_brl"] == 50.0

    evidence = json.loads(body["entry"]["notes"])
    assert evidence["tax_classification_status"] == "USER_DECLARED_PLANNING_ONLY"
    assert evidence["market_scope_source"] == "USER_DECLARATION_NOT_INDEPENDENTLY_VERIFIED"
    assert evidence["market_scope"] == "BR_ELIGIBLE_MARKET"
    assert evidence["instrument"] == "PETR4"
    assert evidence["user_notes"] == "E" * 160
    assert evidence["institution"] == "Intermediária declarada"
    assert evidence["market_label"] == "B3"
    assert evidence["same_asset_confirmed_by_user"] is True
    assert evidence["same_institution_confirmed_by_user"] is True
    assert evidence["same_day_confirmed_by_user"] is True
    assert evidence["independent_market_eligibility_verified"] is False
    assert evidence["tax_liability_confirmed"] is False
    assert evidence["reserve_semantics"] == "PLANNING_ESTIMATE_ONLY"

    owner_id = migrate_fiscal_schema(str(database))
    assert reserve.summary(owner_id)["total_reserved_brl"] == 50.0


def test_manual_day_trade_entry_rejects_missing_confirmation_and_incomplete_criteria(tmp_path, monkeypatch):
    database, reserve = _configure(tmp_path, monkeypatch)

    payload = valid_payload()
    payload["confirmed"] = False
    status, body = _request(payload)
    assert status.startswith("400")
    assert "confirmação explícita" in body["error"]

    payload = valid_payload()
    payload["same_day"] = False
    status, body = _request(payload)
    assert status.startswith("400")
    assert "mesmo ativo, mesma instituição e mesmo dia" in body["error"]

    payload = valid_payload()
    payload["market_scope"] = "FOREIGN_CFD"
    status, body = _request(payload)
    assert status.startswith("400")
    assert "mercado brasileiro elegível" in body["error"]

    owner_id = migrate_fiscal_schema(str(database))
    assert reserve.summary(owner_id)["total_reserved_brl"] == 0.0
