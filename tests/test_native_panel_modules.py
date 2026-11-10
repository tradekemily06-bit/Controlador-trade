from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5"


def test_native_mt5_panel_exposes_reserva_fiscal_and_assistant_navigation():
    source = EA.read_text(encoding="utf-8")
    panel = source.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'SetButton(Obj("V8"),"RF"' in panel
    assert 'SetButton(Obj("V9"),"AE"' in panel
    assert 'active_view="RESERVA"' in events
    assert 'active_view="ASSISTENTE"' in events
    assert "void RenderFiscal()" in source
    assert "void RenderAssistant()" in source
    assert "void RefreshFiscal()" in source
    assert "void RefreshAssistantStatus()" in source


def test_native_mt5_fiscal_view_uses_local_read_only_summary_and_preserves_separation():
    source = EA.read_text(encoding="utf-8")
    fiscal = source.split("void RefreshFiscal()", 1)[1].split("void RefreshAssistantStatus()", 1)[0]

    assert 'Http("GET","/api/fiscal-reserve/local?limit=20"' in fiscal
    assert 'JsonValue(r,"total_reserved_brl")' in fiscal
    assert 'JsonObjectValue(r,"foreign_pending","total")' in fiscal
    assert 'JsonObjectValue(r,"domestic_pending","total")' in fiscal
    assert "fora dos totais" in fiscal
    assert "sem calculo" in fiscal
    assert "REAL: BLOQUEADO" in fiscal


def test_native_mt5_assistant_requires_per_message_consent_and_persists_conversation():
    source = EA.read_text(encoding="utf-8")
    send = source.split("void SendAssistantMessage()", 1)[1].split("void RenderView()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'Http("GET","/api/assistant/local/status"' in source
    assert 'Http("POST","/api/assistant/local/chat"' in send
    assert "if(!assistant_consent_armed)" in send
    assert '"consent_to_openai":true' in send
    assert "assistant_consent_armed=false;" in send
    assert "PersistAssistantConversation();" in send
    assert "LoadAssistantConversation();" in source
    assert 'Obj("ASSISTANT_CONSENT")' in events
    assert 'Obj("ASSISTANT_SEND")' in events
    assert "may_execute_orders" not in send
    assert "execution_allowed" not in send


def test_native_mt5_module_navigation_recreates_base_controls_without_background_polling():
    source = EA.read_text(encoding="utf-8")
    events = source.split("void OnChartEvent", 1)[1]
    timer = source.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    health = source.split("void RefreshHealth()", 1)[1].split("void RefreshSecondary()", 1)[0]

    assert 'active_view="RESERVA"; Panel(); RenderView();' in events
    assert 'active_view="ASSISTENTE"; Panel(); RenderView();' in events
    assert 'else if(active_view=="RESERVA") RefreshFiscal();' not in timer
    assert 'else if(active_view=="ASSISTENTE") RefreshAssistantStatus();' not in timer
    assert 'if(active_view=="RESERVA" || active_view=="ASSISTENTE") return;' in health
