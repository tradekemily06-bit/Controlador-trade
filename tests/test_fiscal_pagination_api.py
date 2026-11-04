import io
import json

import app as app_module
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_schema import migrate_fiscal_schema


def _request(path, query=""):
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "localhost:8000",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body)


def _configure(tmp_path, monkeypatch):
    database = tmp_path / "fiscal-pagination-api.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "pagination-owner")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost")
    monkeypatch.setattr(app_module, "FISCAL_RESERVE_DB", database)
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    owner_id = migrate_fiscal_schema(str(database))
    foreign = FiscalPendingQueue(str(database))
    domestic = FiscalDomesticPendingQueue(str(database))
    monkeypatch.setattr(app_module, "FISCAL_PENDING_QUEUE", foreign)
    monkeypatch.setattr(app_module, "FISCAL_DOMESTIC_PENDING_QUEUE", domestic)

    for number in range(7):
        foreign.add(owner_id, {
            "reference": f"FOREIGN-API-PAGE-{number}",
            "original_amount": number + 1,
            "original_currency": "USD",
            "instrument": "ETF",
            "jurisdiction": "PENDING_REVIEW",
            "occurred_on": f"2026-11-{number + 1:02d}",
        })
        domestic.add(owner_id, {
            "reference": f"BR-API-PAGE-{number}",
            "category_candidate": "BR_COMMON_EXCHANGE",
            "instrument": "ETF",
            "market_scope": "B3",
            "occurred_on": f"2026-11-{number + 1:02d}",
        })

    # Another owner's rows must not affect the authenticated owner's page or total.
    foreign.add("another-owner", {
        "reference": "FOREIGN-OTHER-OWNER",
        "original_amount": 999,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "PENDING_REVIEW",
        "occurred_on": "2026-11-30",
    })
    domestic.add("another-owner", {
        "reference": "BR-OTHER-OWNER",
        "instrument": "ETF",
        "occurred_on": "2026-11-30",
    })
    return owner_id


def _assert_three_pages(path, reference_prefix):
    pages = []
    for offset in (0, 3, 6):
        status, payload = _request(path, f"limit=3&offset={offset}")
        assert status.startswith("200")
        assert payload["total"] == 7
        pages.extend(item["reference"] for item in payload["items"])

    assert len(pages) == len(set(pages)) == 7
    assert all(reference.startswith(reference_prefix) for reference in pages)
    assert "OTHER-OWNER" not in json.dumps(pages)


def test_foreign_pending_http_pagination_is_owner_scoped(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _assert_three_pages("/api/fiscal-reserve/pending", "FOREIGN-API-PAGE-")


def test_domestic_pending_http_pagination_is_owner_scoped(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _assert_three_pages("/api/fiscal-reserve/domestic-pending", "BR-API-PAGE-")


def test_pending_http_pagination_rejects_invalid_parameters(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    for path in (
        "/api/fiscal-reserve/pending",
        "/api/fiscal-reserve/domestic-pending",
    ):
        for query in ("limit=0", "limit=501", "offset=-1", "limit=abc"):
            status, payload = _request(path, query)
            assert status.startswith("400")
            assert payload["error"] == "Entrada inválida"
