from datetime import date
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from streamlit.testing.v1 import AppTest


PANEL_APP = Path(__file__).resolve().parents[1] / "streamlit_panel" / "app.py"


def _summary():
    today = date.today()
    bounds = {
        "day": (today, today),
        "week": (date.fromordinal(today.toordinal() - today.weekday()), today),
        "month": (today.replace(day=1), today),
        "year": (today.replace(month=1, day=1), today),
    }
    return {
        "as_of": today.isoformat(),
        "categories": {
            "BR_DAY_TRADE": {
                "entries": 0, "rate": 20.0, "realized_result_brl": 0.0,
                "reserve_amount_brl": 0.0, "rate_source": "USER_CONFIGURED",
            },
            "FOREIGN_FINANCIAL_ASSET": {
                "entries": 0, "classification_status": "PENDING_CLASSIFICATION",
                "rate_available": False, "realized_result_brl": 0.0,
                "reserve_amount_brl": 0.0,
            },
        },
        "periods": {
            key: {
                "start": start.isoformat(), "end": end.isoformat(), "entries": 0,
                "realized_result_brl": 0.0, "reserve_amount_brl": 0.0,
            }
            for key, (start, end) in bounds.items()
        },
        "total_reserved_brl": 0.0,
        "reserve_semantics": {
            "kind": "PLANNING_ESTIMATE_ONLY", "tax_liability_confirmed": False,
            "monthly_tax_assessment": False, "monthly_loss_offsets_calculated": False,
            "irrf_credits_calculated": False,
        },
        "foreign_pending": {
            "available": False, "included_in_totals": False, "reserve_calculated": False,
        },
        "history": [],
        "history_page": {"total": 0, "limit": 50, "offset": 0, "returned": 0, "has_more": False},
        "monthly_planning": None,
    }


def _panel_with_http(monkeypatch):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/fiscal-reserve?"):
                return self._send(_summary())
            # Queue reads are deliberately unavailable here: this test isolates
            # the write contract and must not mistake unavailable reviews for totals.
            return self._send({"error": "not found"}, 404)

        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size) or b"{}")
            calls.append((self.path, payload))
            return self._send({"created": True, "pending_id": "pending-test-001"})

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("CONTROLADOR_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")
    app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("RESERVA FISCAL").run(timeout=30)
    assert not app.exception
    return app, calls, server, worker


def _set_text(app, label, value):
    next(item for item in app.text_input if item.label == label).set_value(value)


def test_domestic_pending_form_posts_separate_unclassified_evidence(monkeypatch):
    app, calls, server, worker = _panel_with_http(monkeypatch)
    try:
        _set_text(app, "Referência / comprovante · Brasil", "BR-PENDING-001")
        _set_text(app, "Ativo ou instrumento · Brasil", "WIN")
        _set_text(app, "Mercado / ambiente", "B3")
        app.button(key="FormSubmitter:domestic_pending_form-Guardar pendência brasileira").click().run(timeout=30)

        assert not app.exception
        posts = [payload for path, payload in calls if path == "/api/fiscal-reserve/domestic-pending"]
        assert len(posts) == 1
        assert posts[0]["reference"] == "BR-PENDING-001"
        assert posts[0]["instrument"] == "WIN"
        assert posts[0]["market_scope"] == "B3"
        assert "realized_result_brl" not in posts[0]
        assert not any(path in {"/api/fiscal-reserve/results", "/api/fiscal-reserve/rates"} for path, _ in calls)
        assert any("Nenhum cálculo foi realizado" in item.value for item in app.success)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_foreign_pending_form_preserves_original_currency_and_optional_fx_evidence(monkeypatch):
    app, calls, server, worker = _panel_with_http(monkeypatch)
    try:
        _set_text(app, "Referência / comprovante", "FOREIGN-PENDING-001")
        next(item for item in app.number_input if item.label == "Valor original").set_value(250.75)
        _set_text(app, "Instrumento", "ETF")
        _set_text(app, "Jurisdição", "EUA")
        _set_text(app, "Corretora / instituição", "Broker Demo")
        _set_text(app, "Local de custódia (país, instituição ou autocustódia)", "EUA")
        _set_text(app, "Tipo / especificação do contrato", "ETF à vista")
        app.button(key="FormSubmitter:foreign_pending_form-Guardar como pendente").click().run(timeout=30)

        assert not app.exception
        posts = [payload for path, payload in calls if path == "/api/fiscal-reserve/pending"]
        assert len(posts) == 1
        payload = posts[0]
        assert payload["reference"] == "FOREIGN-PENDING-001"
        assert payload["original_amount"] == 250.75
        assert payload["original_currency"] == "USD"
        assert payload["instrument"] == "ETF"
        assert payload["jurisdiction"] == "EUA"
        assert payload["fx_conversion_method"] == "NOT_INFORMED"
        assert "fx_rate" not in payload
        assert "realized_result_brl" not in payload
        assert not any(path == "/api/fiscal-reserve/results" for path, _ in calls)
        assert any("Nenhum cálculo foi feito" in item.value for item in app.success)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_foreign_signed_result_keeps_negative_sign_and_is_not_booked_as_domestic_result(monkeypatch):
    app, calls, server, worker = _panel_with_http(monkeypatch)
    try:
        _set_text(app, "Referência do extrato", "FOREIGN-LOSS-001")
        next(item for item in app.number_input if item.label == "Resultado original (+ lucro / - prejuízo)").set_value(-42.375)
        _set_text(app, "Instrumento", "Ação")
        _set_text(app, "Jurisdição", "EUA")
        _set_text(app, "Corretora / instituição", "Broker Demo")
        _set_text(app, "Local de custódia", "EUA")
        _set_text(app, "Tipo / especificação do contrato", "Ação ordinária")
        app.button(key="FormSubmitter:foreign_signed_result-Guardar como pendente").click().run(timeout=30)

        assert not app.exception
        posts = [payload for path, payload in calls if path == "/api/fiscal-reserve/pending-result"]
        assert len(posts) == 1
        payload = posts[0]
        assert payload["reference"] == "FOREIGN-LOSS-001"
        assert payload["original_result"] == -42.375
        assert payload["original_currency"] == "USD"
        assert payload["instrument"] == "Ação"
        assert not any(path in {"/api/fiscal-reserve/results", "/api/fiscal-reserve/domestic-pending"} for path, _ in calls)
        assert any("sinal original" in item.value for item in app.success)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
