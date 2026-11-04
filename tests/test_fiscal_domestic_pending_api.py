import io
import json

import app as app_module
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_schema import migrate_fiscal_schema


def _request(path, *, method="GET", query="", payload=None):
    raw = json.dumps(payload or {}).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
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


def _configure(tmp_path, monkeypatch):
    database = tmp_path / "fiscal-domestic-api.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "domestic-api-owner")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    queue = FiscalDomesticPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", queue)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)
    owner_id = migrate_fiscal_schema(str(database))
    return queue, owner_id


def test_domestic_pending_api_is_owner_scoped_and_ignores_forged_owner(
    tmp_path, monkeypatch
):
    queue, owner_id = _configure(tmp_path, monkeypatch)
    payload = {
        "reference": "BR-API-OWNER-001",
        "category_candidate": "BR_COMMON_EXCHANGE",
        "instrument": "ETF",
        "market_scope": "B3",
        "occurred_on": "2026-11-04",
        "realized_result_brl": -75.25,
    }
    queue.add("other-owner", {
        **payload,
        "reference": "BR-API-OTHER-OWNER",
    })

    status, created = _request(
        "/api/fiscal-reserve/domestic-pending",
        method="POST",
        payload=payload,
    )
    assert status.startswith("201")
    assert created["pending"]["realized_result_brl"] == -75.25
    assert created["classification_status"] == "PENDING_CLASSIFICATION"
    assert created["reserve_calculated"] is False

    status, listing = _request(
        "/api/fiscal-reserve/domestic-pending",
        query="owner_id=other-owner",
    )
    assert status.startswith("200")
    assert listing["total"] == 1
    assert [item["reference"] for item in listing["items"]] == [
        "BR-API-OWNER-001"
    ]
    assert "BR-API-OTHER-OWNER" not in json.dumps(listing)

    status, summary = _request(
        "/api/fiscal-reserve/domestic-pending/summary",
        query="owner_id=other-owner",
    )
    assert status.startswith("200")
    assert summary["total"] == 1
    assert summary["periods"]["day"]["results"] == 1
    assert summary["included_in_totals"] is False
    assert summary["reserve_calculated"] is False


def test_domestic_pending_api_rejects_duplicate_reference(tmp_path, monkeypatch):
    _queue, _owner_id = _configure(tmp_path, monkeypatch)
    payload = {
        "reference": "BR-API-DUPLICATE",
        "instrument": "Ação",
        "occurred_on": "2026-11-04",
    }

    first_status, _ = _request(
        "/api/fiscal-reserve/domestic-pending",
        method="POST",
        payload=payload,
    )
    second_status, duplicate = _request(
        "/api/fiscal-reserve/domestic-pending",
        method="POST",
        payload=payload,
    )

    assert first_status.startswith("201")
    assert second_status.startswith("409")
    assert "Já existe" in duplicate["error"]
