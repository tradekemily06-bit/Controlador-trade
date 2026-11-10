from pathlib import Path

from streamlit.testing.v1 import AppTest


PANEL_APP = Path(__file__).resolve().parents[1] / "streamlit_panel" / "app.py"


def _open_panel(monkeypatch):
    # Keep the test isolated from a real runtime or broker.
    monkeypatch.setenv("CONTROLADOR_API_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")
    app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
    assert not app.exception
    return app


def test_streamlit_panel_starts_and_exposes_the_expected_main_areas(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    assert list(area.options) == [
        "COCKPIT",
        "ANÁLISE",
        "ESTUDO",
        "FINANCEIRO",
        "RESERVA FISCAL",
        "ASSISTENTE DO ECOSSISTEMA",
        "CENTRAL",
    ]


def test_streamlit_assistant_is_a_separate_main_area_with_explicit_consent(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("ASSISTENTE DO ECOSSISTEMA").run(timeout=30)

    assert not app.exception
    assert any(item.value == "Assistente do Ecossistema" for item in app.subheader)
    assert any("Autorizo enviar minha pergunta" in item.label for item in app.checkbox)


def test_streamlit_fiscal_reserve_is_a_separate_main_area(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("RESERVA FISCAL").run(timeout=30)

    assert not app.exception
    assert any(item.value == "Reserva Fiscal" for item in app.subheader)



def test_streamlit_fiscal_mutation_forms_stay_hidden_when_summary_is_unavailable(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("RESERVA FISCAL").run(timeout=30)

    assert not app.exception
    assert any(
        "Resumo fiscal indisponível" in item.value
        or "Resumo fiscal incompleto ou inválido" in item.value
        for item in app.error
    )
    # No fiscal form may be rendered from an unavailable or unvalidated snapshot.
    visible_inputs = {item.label for item in app.text_input}
    assert "Ativo / instrumento negociado" not in visible_inputs
    assert "Referência / comprovante" not in visible_inputs
    assert "Referência / comprovante · Brasil" not in visible_inputs


def test_streamlit_assistant_consent_is_disabled_without_owner_identity(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_SINGLE_USER_IDENTITY", raising=False)
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("ASSISTENTE DO ECOSSISTEMA").run(timeout=30)

    consent = next(item for item in app.checkbox if "Autorizo enviar minha pergunta" in item.label)
    assert consent.disabled is True
    assert not app.exception


def test_streamlit_financeiro_has_its_own_main_area(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("FINANCEIRO").run(timeout=30)

    assert not app.exception
    assert not any(item.label == "Módulos" for item in app.radio)
    assert any(item.value == "Financeiro" for item in app.subheader)



def test_kill_switch_panel_requires_reason_and_explicit_confirmation(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("COCKPIT").run(timeout=30)
    module = next(item for item in app.radio if item.label == "Módulos")
    assert "Kill Switch" in list(module.options)
    module.set_value("Kill Switch").run(timeout=30)

    assert not app.exception
    assert any(item.value == "Proteção operacional · Kill Switch" for item in app.subheader)
    assert any(item.label == "Motivo obrigatório da ativação" for item in app.text_input)
    assert any(
        item.label == "Confirmo que quero bloquear novas execuções neste runtime."
        for item in app.checkbox
    )
    assert any(item.label == "Ativar Kill Switch" for item in app.button)



def test_all_streamlit_module_destinations_render_without_uncaught_exceptions(monkeypatch):
    app = _open_panel(monkeypatch)
    for area_name in ("COCKPIT", "ANÁLISE", "ESTUDO", "FINANCEIRO", "RESERVA FISCAL", "ASSISTENTE DO ECOSSISTEMA", "CENTRAL"):
        area = next(item for item in app.radio if item.label == "Áreas principais")
        area.set_value(area_name).run(timeout=30)
        assert not app.exception, f"area failed to render: {area_name}"

        if area_name in {"FINANCEIRO", "RESERVA FISCAL", "ASSISTENTE DO ECOSSISTEMA"}:
            expected_heading = {
                "FINANCEIRO": "Financeiro",
                "RESERVA FISCAL": "Reserva Fiscal",
                "ASSISTENTE DO ECOSSISTEMA": "Assistente do Ecossistema",
            }[area_name]
            assert any(item.value == expected_heading for item in app.subheader), f"dedicated area failed to render: {area_name}"
            continue

        module = next(item for item in app.radio if item.label == "Módulos")
        for module_name in list(module.options):
            module = next(item for item in app.radio if item.label == "Módulos")
            module.set_value(module_name).run(timeout=30)
            assert not app.exception, f"module failed to render: {area_name} / {module_name}"
            assert not any("ainda não possui integração operacional" in item.value.lower() for item in app.info), f"placeholder module: {area_name} / {module_name}"


def test_assistant_provider_connection_button_calls_runtime_and_reports_success(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path == "/api/assistant/status":
                return self._send({
                    "available": True,
                    "message": "Credenciais configuradas; conexão ainda não testada.",
                    "model": "modelo-de-teste",
                })
            if self.path == "/api/assistant/conversations":
                return self._send({"conversations": []})
            if self.path == "/api/runtime/analysis/latest":
                return self._send({"available": False, "analysis": None})
            if self.path == "/api/health":
                return self._send({
                    "health": "OK",
                    "execution_allowed": False,
                    "real": "DESABILITADO",
                    "components": {},
                })
            if self.path == "/api/preferences":
                return self._send({"preferences": {}})
            return self._send({"error": "not found"}, 404)

        def do_POST(self):
            calls.append(("POST", self.path))
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/assistant/test-connection":
                assert payload == {}
                return self._send({"success": True, "connection_tested": True})
            return self._send({"error": "not found"}, 404)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv(
            "CONTROLADOR_API_BASE_URL",
            f"http://127.0.0.1:{server.server_port}",
        )
        monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
        monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
        monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")

        app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
        area = next(item for item in app.radio if item.label == "Áreas principais")
        area.set_value("ASSISTENTE DO ECOSSISTEMA").run(timeout=30)

        assert not app.exception
        button = next(
            item for item in app.button
            if item.label == "Testar conexão com a OpenAI"
        )
        button.click().run(timeout=30)

        assert not app.exception
        assert ("POST", "/api/assistant/test-connection") in calls
        assert any(
            "Conexão com a OpenAI testada com sucesso" in item.value
            for item in app.success
        )
        assert any(
            "Nenhuma pergunta, conversa ou dado fiscal foi enviado neste teste."
            in item.value
            for item in app.success
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)



def test_assistant_question_requires_consent_and_posts_only_after_explicit_authorization(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []
    received_chat = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path == "/api/assistant/status":
                return self._send({"available": True, "message": "Provedor pronto.", "model": "modelo-teste"})
            if self.path == "/api/assistant/conversations":
                return self._send({"conversations": []})
            if self.path == "/api/runtime/analysis/latest":
                return self._send({"available": False, "analysis": None})
            if self.path == "/api/health":
                return self._send({"health": "OK", "execution_allowed": False, "real": "DESABILITADO", "components": {}})
            if self.path == "/api/preferences":
                return self._send({"preferences": {}})
            return self._send({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            calls.append(("POST", self.path))
            if self.path == "/api/assistant/chat":
                received_chat.append(payload)
                return self._send({
                    "conversation_id": "conversation-test-001",
                    "answer": "Resposta simulada do Assistente.",
                })
            return self._send({"error": "not found"}, 404)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("CONTROLADOR_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
        monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
        monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")

        app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
        area = next(item for item in app.radio if item.label == "Áreas principais")
        area.set_value("ASSISTENTE DO ECOSSISTEMA").run(timeout=30)

        assert not app.exception
        assert not any(method == "POST" and path == "/api/assistant/chat" for method, path in calls)

        consent = next(item for item in app.checkbox if "Autorizo enviar minha pergunta" in item.label)
        consent.check().run(timeout=30)
        assert not app.exception

        chat = next(item for item in app.chat_input)
        chat.set_value("Explique meu resumo operacional.").run(timeout=30)

        assert not app.exception
        assert len(received_chat) == 1
        assert received_chat[0]["message"] == "Explique meu resumo operacional."
        assert received_chat[0]["consent_to_openai"] is True
        assert received_chat[0]["conversation_id"] is None
        assert app.session_state["assistant_conversation_id"] == "conversation-test-001"
        assert {"role": "user", "content": "Explique meu resumo operacional."} in app.session_state["assistant_history"]
        assert {"role": "assistant", "content": "Resposta simulada do Assistente."} in app.session_state["assistant_history"]
        assert app.session_state["assistant_openai_consent"] is False
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)



def test_assistant_saved_conversation_can_be_opened_and_deleted_from_panel(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path == "/api/assistant/status":
                return self._send({"available": True, "message": "Provedor pronto.", "model": "modelo-teste"})
            if self.path == "/api/assistant/conversations":
                return self._send({"conversations": [{
                    "conversation_id": "conversation-saved-001",
                    "title": "Revisão de risco",
                    "updated_at": "2026-11-10T12:00:00-03:00",
                }]})
            if self.path == "/api/assistant/history?conversation_id=conversation-saved-001":
                return self._send({"messages": [
                    {"role": "user", "content": "Revise meu risco."},
                    {"role": "assistant", "content": "Vamos conferir os limites."},
                ]})
            if self.path == "/api/runtime/analysis/latest":
                return self._send({"available": False, "analysis": None})
            if self.path == "/api/health":
                return self._send({"health": "OK", "execution_allowed": False, "real": "DESABILITADO", "components": {}})
            if self.path == "/api/preferences":
                return self._send({"preferences": {}})
            return self._send({"error": "not found"}, 404)

        def do_DELETE(self):
            calls.append(("DELETE", self.path))
            if self.path == "/api/assistant/conversations?conversation_id=conversation-saved-001":
                return self._send({"deleted": True})
            return self._send({"error": "not found"}, 404)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("CONTROLADOR_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
        monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
        monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")

        app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
        area = next(item for item in app.radio if item.label == "Áreas principais")
        area.set_value("ASSISTENTE DO ECOSSISTEMA").run(timeout=30)
        assert not app.exception
        assert any(item.label == "Conversas anteriores" for item in app.selectbox)

        app.button(key="load_assistant_conversation").click().run(timeout=30)
        assert not app.exception
        assert ("GET", "/api/assistant/history?conversation_id=conversation-saved-001") in calls
        assert app.session_state["assistant_conversation_id"] == "conversation-saved-001"
        assert {"role": "user", "content": "Revise meu risco."} in app.session_state["assistant_history"]
        assert {"role": "assistant", "content": "Vamos conferir os limites."} in app.session_state["assistant_history"]

        app.button(key="delete_assistant_conversation").click().run(timeout=30)
        assert not app.exception
        assert ("DELETE", "/api/assistant/conversations?conversation_id=conversation-saved-001") in calls
        assert app.session_state["assistant_conversation_id"] is None
        assert app.session_state["assistant_history"] == []
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)



def test_fiscal_rate_form_posts_only_configured_brazil_day_trade_rate(monkeypatch):
    import json
    import threading
    from datetime import date
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []
    current_rate = {"value": 20.0}
    as_of = date.today().isoformat()
    start_week = date.fromordinal(date.today().toordinal() - date.today().weekday()).isoformat()
    start_month = date.today().replace(day=1).isoformat()
    start_year = date.today().replace(month=1, day=1).isoformat()

    def summary_payload():
        bounds = {
            "day": (as_of, as_of),
            "week": (start_week, as_of),
            "month": (start_month, as_of),
            "year": (start_year, as_of),
        }
        periods = {
            key: {
                "start": start, "end": end, "entries": 0,
                "realized_result_brl": 0.0, "reserve_amount_brl": 0.0,
            }
            for key, (start, end) in bounds.items()
        }
        return {
            "as_of": as_of,
            "categories": {
                "BR_DAY_TRADE": {
                    "entries": 0, "rate": current_rate["value"],
                    "realized_result_brl": 0.0, "reserve_amount_brl": 0.0,
                    "rate_source": "USER_CONFIGURED",
                },
                "FOREIGN_FINANCIAL_ASSET": {
                    "entries": 0, "classification_status": "PENDING_CLASSIFICATION",
                    "rate_available": False, "realized_result_brl": 0.0,
                    "reserve_amount_brl": 0.0,
                },
            },
            "periods": periods,
            "total_reserved_brl": 0.0,
            "reserve_semantics": {
                "kind": "PLANNING_ESTIMATE_ONLY",
                "tax_liability_confirmed": False,
                "monthly_tax_assessment": False,
                "monthly_loss_offsets_calculated": False,
                "irrf_credits_calculated": False,
                "description": "Estimativa de planejamento, não imposto devido.",
            },
            "foreign_pending": {
                "available": False, "included_in_totals": False,
                "reserve_calculated": False,
            },
            "history": [],
            "history_page": {
                "total": 0, "limit": 50, "offset": 0,
                "returned": 0, "has_more": False,
            },
            "monthly_planning": None,
        }

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path.startswith("/api/fiscal-reserve?"):
                return self._send(summary_payload())
            return self._send({})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            calls.append(("POST", self.path, payload))
            if self.path == "/api/fiscal-reserve/rates":
                current_rate["value"] = payload["rates"]["BR_DAY_TRADE"]
                return self._send({"updated": True})
            return self._send({"error": "not found"}, 404)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("CONTROLADOR_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
        monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
        monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")

        app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
        area = next(item for item in app.radio if item.label == "Áreas principais")
        area.set_value("RESERVA FISCAL").run(timeout=30)
        assert not app.exception

        rate_input = next(item for item in app.number_input if item.label == "Percentual para novos lançamentos")
        rate_input.set_value(17.5)
        app.run(timeout=30)
        app.button(key="fiscal_rate_form-Salvar percentual").click().run(timeout=30)

        assert not app.exception
        posts = [item for item in calls if item[0] == "POST"]
        assert len(posts) == 1
        assert posts[0][1] == "/api/fiscal-reserve/rates"
        assert posts[0][2] == {"rates": {"BR_DAY_TRADE": 17.5}}
        assert current_rate["value"] == 17.5
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)



def test_fiscal_result_requires_confirmation_and_complete_fields_before_posting(monkeypatch):
    import json
    import threading
    from datetime import date
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []
    saved = []
    as_of = date.today().isoformat()
    week = date.fromordinal(date.today().toordinal() - date.today().weekday()).isoformat()
    month = date.today().replace(day=1).isoformat()
    year = date.today().replace(month=1, day=1).isoformat()

    def summary_payload():
        bounds = {
            "day": (as_of, as_of), "week": (week, as_of),
            "month": (month, as_of), "year": (year, as_of),
        }
        periods = {}
        for name, (start, end) in bounds.items():
            periods[name] = {
                "start": start, "end": end, "entries": len(saved),
                "realized_result_brl": 125.0 if saved else 0.0,
                "reserve_amount_brl": 25.0 if saved else 0.0,
            }
        history = [{
            "entry_id": "entry-test-001", "category": "BR_DAY_TRADE",
            "reference": saved[0]["reference"], "occurred_on": as_of,
            "notes": saved[0]["notes"],
        }] if saved else []
        return {
            "as_of": as_of,
            "categories": {
                "BR_DAY_TRADE": {
                    "entries": len(saved), "rate": 20.0,
                    "realized_result_brl": 125.0 if saved else 0.0,
                    "reserve_amount_brl": 25.0 if saved else 0.0,
                    "rate_source": "USER_CONFIGURED",
                },
                "FOREIGN_FINANCIAL_ASSET": {
                    "entries": 0, "classification_status": "PENDING_CLASSIFICATION",
                    "rate_available": False, "realized_result_brl": 0.0,
                    "reserve_amount_brl": 0.0,
                },
            },
            "periods": periods,
            "total_reserved_brl": 25.0 if saved else 0.0,
            "reserve_semantics": {
                "kind": "PLANNING_ESTIMATE_ONLY", "tax_liability_confirmed": False,
                "monthly_tax_assessment": False, "monthly_loss_offsets_calculated": False,
                "irrf_credits_calculated": False,
                "description": "Estimativa de planejamento, não imposto devido.",
            },
            "foreign_pending": {
                "available": False, "included_in_totals": False,
                "reserve_calculated": False,
            },
            "history": history,
            "history_page": {
                "total": len(history), "limit": 50, "offset": 0,
                "returned": len(history), "has_more": False,
            },
            "monthly_planning": None,
        }

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path.startswith("/api/fiscal-reserve?"):
                return self._send(summary_payload())
            return self._send({})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            calls.append(("POST", self.path, payload))
            if self.path == "/api/fiscal-reserve/results":
                saved.append(payload)
                return self._send({"created": True, "entry_id": "entry-test-001"})
            return self._send({"error": "not found"}, 404)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("CONTROLADOR_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
        monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "test-owner")
        monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")

        app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
        area = next(item for item in app.radio if item.label == "Áreas principais")
        area.set_value("RESERVA FISCAL").run(timeout=30)
        assert not app.exception

        submit_key = "fiscal_result_form-Registrar estimativa de planejamento"
        app.button(key=submit_key).click().run(timeout=30)
        assert not app.exception
        assert not [item for item in calls if item[0] == "POST"]
        assert any("Confirme os critérios de day trade" in item.value for item in app.error)

        next(item for item in app.checkbox if "Confirmo que foi o mesmo ativo" in item.label).check()
        app.run(timeout=30)
        app.button(key=submit_key).click().run(timeout=30)
        assert not app.exception
        assert not [item for item in calls if item[0] == "POST"]
        assert any("Preencha ativo, instituição, mercado e referência" in item.value for item in app.error)

        next(item for item in app.number_input if item.label == "Resultado realizado (R$)").set_value(125.0)
        for label, value in (
            ("Ativo / instrumento negociado", "WIN"),
            ("Instituição intermediária", "Corretora Demo"),
            ("Mercado / ambiente de negociação", "B3"),
            ("Referência / comprovante", "comprovante-teste-001"),
        ):
            next(item for item in app.text_input if item.label == label).set_value(value)
        app.run(timeout=30)
        app.button(key=submit_key).click().run(timeout=30)

        assert not app.exception
        posts = [item for item in calls if item[0] == "POST"]
        assert len(posts) == 1
        payload = posts[0][2]
        assert payload["category"] == "BR_DAY_TRADE"
        assert payload["realized_result_brl"] == 125.0
        assert payload["instrument"] == "WIN"
        assert payload["institution"] == "Corretora Demo"
        assert payload["market_label"] == "B3"
        assert payload["market_scope"] == "BR_ELIGIBLE_MARKET"
        assert payload["same_asset"] is True
        assert payload["same_institution"] is True
        assert payload["same_day"] is True
        assert payload["confirmed"] is True
        assert payload["reference"] == "comprovante-teste-001"
        assert saved
        post_index = next(index for index, item in enumerate(calls) if item[0] == "POST")
        assert any(
            index > post_index and item[0] == "GET" and item[1].startswith("/api/fiscal-reserve?")
            for index, item in enumerate(calls)
        )
        assert app.dataframe, "the refreshed fiscal history should render the saved result"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
