import io
import json

import app as app_module
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema


def _configure(tmp_path, monkeypatch):
    database = tmp_path / "foreign-planning.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "foreign-planning-owner")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    owner_id = migrate_fiscal_schema(str(database))
    reserve = FiscalReserve(str(database))
    queue = FiscalPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_RESERVE", reserve)
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", queue)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    return database, owner_id, reserve, queue


def _request(path, payload):
    raw = json.dumps(payload).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": path,
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


def _pending_payload(reference="FOREIGN-PLANNING-001", **overrides):
    payload = {
        "reference": reference,
        "original_result": 100.0,
        "original_currency": "USD",
        "instrument": "Forex",
        "jurisdiction": "Estados Unidos",
        "occurred_on": "2026-11-05",
        "fx_rate": 5.0,
        "fx_date": "2026-11-05",
        "fx_source": "Banco Central do Brasil - PTAX venda",
        "fx_conversion_method": "PTAX_SELL",
        "tax_residency_at_event": "BRAZIL",
        "income_nature": "TRADING_RESULT",
        "event_type": "DISPOSAL",
        "institution": "Corretora estrangeira",
        "custody_location": "Custódia estrangeira",
        "contract_type": "Contrato Forex",
    }
    payload.update(overrides)
    return payload


def test_foreign_financial_investment_estimate_requires_explicit_confirmation_and_is_owner_scoped(
    tmp_path, monkeypatch
):
    _database, owner_id, reserve, queue = _configure(tmp_path, monkeypatch)
    pending = queue.add_realized_result(owner_id, _pending_payload())

    missing_confirmation, _ = _request(
        "/api/fiscal-reserve/foreign-planning-estimate",
        {
            "pending_id": pending["pending_id"],
            "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
            "confirmed": False,
        },
    )
    assert missing_confirmation.startswith("400")
    assert reserve.summary(owner_id)["total_reserved_brl"] == 0.0

    status, body = _request(
        "/api/fiscal-reserve/foreign-planning-estimate",
        {
            "pending_id": pending["pending_id"],
            "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
            "confirmed": True,
            "owner_id": "forged-owner-is-ignored",
        },
    )

    assert status.startswith("201")
    assert body["classification_status"] == "USER_DECLARED_PLANNING_ONLY"
    assert body["tax_liability_confirmed"] is False
    assert body["reserve_is_estimate"] is True
    assert body["entry"]["realized_result_brl"] == 500.0
    assert body["entry"]["reserve_rate"] == 15.0
    assert body["entry"]["reserve_amount_brl"] == 75.0
    assert body["fx_quote_verified"] is False
    assert body["fx_source_verified"] is False

    evidence = json.loads(body["entry"]["notes"])
    assert evidence["source_pending_id"] == pending["pending_id"]
    assert evidence["tax_residency_at_event"] == "BRAZIL"
    assert evidence["income_nature"] == "TRADING_RESULT"
    assert evidence["event_type"] == "DISPOSAL"
    assert evidence["instrument"] == "Forex"
    assert evidence["jurisdiction"] == "Estados Unidos"
    assert evidence["foreign_tax_credit_applied"] is False
    assert evidence["loss_offsets_applied"] is False
    assert evidence["legal_rate"] == 15.0
    assert evidence["fx_quote_verification"] == "USER_DECLARED_NOT_VERIFIED"
    assert evidence["fx_source_verification"] == "USER_DECLARED_NOT_VERIFIED"

    summary = reserve.summary(owner_id)
    assert summary["total_reserved_brl"] == 75.0
    assert summary["categories"]["BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT"]["reserve_amount_brl"] == 75.0
    assert queue.get_pending(owner_id, pending["pending_id"])["planning_estimate_registered"] is True
    assert queue.summary(owner_id)["planning_estimates_registered"] == 1

    duplicate_status, _ = _request(
        "/api/fiscal-reserve/foreign-planning-estimate",
        {
            "pending_id": pending["pending_id"],
            "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
            "confirmed": True,
        },
    )
    assert duplicate_status.startswith("409")
    assert reserve.summary(owner_id)["total_reserved_brl"] == 75.0


def test_foreign_planning_estimate_rejects_unqualified_records_and_missing_fx(tmp_path, monkeypatch):
    _database, owner_id, reserve, queue = _configure(tmp_path, monkeypatch)
    invalid_items = [
        _pending_payload("FOREIGN-NON-BRAZIL-001", tax_residency_at_event="FOREIGN"),
        _pending_payload("FOREIGN-CRYPTO-001"),
        _pending_payload("FOREIGN-NO-FX-001", fx_rate=None, fx_date=None, fx_source="", fx_conversion_method="NOT_CONVERTED"),
        _pending_payload("FOREIGN-WRONG-FX-DATE-001", fx_date="2026-11-04"),
        _pending_payload("FOREIGN-NON-PTAX-001", fx_conversion_method="BROKER_STATEMENT"),
        _pending_payload("FOREIGN-NON-BCB-SOURCE-001", fx_source="Extrato da corretora"),
        _pending_payload("FOREIGN-TRANSFER-001", event_type="TRANSFER"),
        _pending_payload("FOREIGN-OTHER-NATURE-001", income_nature="OTHER"),
        _pending_payload("FOREIGN-BEFORE-LAW-001", occurred_on="2023-12-31"),
        _pending_payload("FOREIGN-NO-INSTITUTION-001", institution=""),
        _pending_payload("FOREIGN-NO-CUSTODY-001", custody_location="NOT_INFORMED"),
        _pending_payload("FOREIGN-NO-CONTRACT-001", contract_type="NOT_INFORMED"),
    ]
    for payload in invalid_items:
        pending = queue.add_realized_result(owner_id, payload)
        category = (
            "FOREIGN_CRYPTO"
            if pending["reference"] == "FOREIGN-CRYPTO-001"
            else "FOREIGN_FINANCIAL_INVESTMENT"
        )
        status, _ = _request(
            "/api/fiscal-reserve/foreign-planning-estimate",
            {
                "pending_id": pending["pending_id"],
                "candidate_classification": category,
                "confirmed": True,
            },
        )
        assert status.startswith("400"), pending["reference"]

    assert reserve.summary(owner_id)["total_reserved_brl"] == 0.0


def test_foreign_estimate_keeps_forex_cfd_futures_and_crypto_pending(tmp_path, monkeypatch):
    _database, owner_id, reserve, queue = _configure(tmp_path, monkeypatch)
    unsupported = [
        _pending_payload("UNSUPPORTED-CFD", instrument="Índice S&P 500", contract_type="CFD"),
        _pending_payload("UNSUPPORTED-FUTURES", instrument="Futures", contract_type="Contrato futuro"),
        _pending_payload("UNSUPPORTED-CRYPTO", instrument="Bitcoin", contract_type="Spot crypto"),
    ]
    for payload in unsupported:
        pending = queue.add_realized_result(owner_id, payload)
        status, body = _request(
            "/api/fiscal-reserve/foreign-planning-estimate",
            {
                "pending_id": pending["pending_id"],
                "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
                "confirmed": True,
            },
        )
        assert status.startswith("400"), payload["reference"]
        assert body["error"] == "Entrada inválida"

    assert reserve.summary(owner_id)["total_reserved_brl"] == 0.0
    assert queue.summary(owner_id)["planning_estimates_registered"] == 0


def test_foreign_loss_is_recorded_but_does_not_create_negative_reserve(tmp_path, monkeypatch):
    _database, owner_id, reserve, queue = _configure(tmp_path, monkeypatch)
    pending = queue.add_realized_result(
        owner_id,
        _pending_payload("FOREIGN-PLANNING-LOSS-001", original_result=-40.0),
    )

    status, body = _request(
        "/api/fiscal-reserve/foreign-planning-estimate",
        {
            "pending_id": pending["pending_id"],
            "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
            "confirmed": True,
        },
    )

    assert status.startswith("201")
    assert body["entry"]["realized_result_brl"] == -200.0
    assert body["entry"]["reserve_amount_brl"] == 0.0
    assert reserve.summary(owner_id)["total_reserved_brl"] == 0.0
