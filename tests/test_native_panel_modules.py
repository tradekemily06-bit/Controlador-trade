from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5"


def test_native_mt5_panel_exposes_reserva_fiscal_and_assistant_navigation():
    source = EA.read_text(encoding="utf-8")
    panel = source.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'string area_labels[6]={"COCKPIT","ANÁLISE","ESTUDO","FISCAL","ASSIST.","CENTRAL"};' in source
    assert 'SetButton(area_button,area_labels[i]' in source
    assert 'SelectArea("RESERVA FISCAL")' in events
    assert 'SelectArea("ASSISTENTE DO ECOSSISTEMA")' in events
    assert 'SelectArea("CENTRAL")' in events
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
    assert r'\"consent_to_openai\":true' in send
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
    clear_fields = source.split("void ClearCockpitFields()", 1)[1].split("void ClearAssistantControls()", 1)[0]

    assert 'SelectArea("RESERVA FISCAL")' in events
    assert 'SelectArea("ASSISTENTE DO ECOSSISTEMA")' in events
    assert 'SelectArea("CENTRAL")' in events
    assert 'else if(active_view=="RESERVA") RefreshFiscal();' not in timer
    assert 'else if(active_view=="ASSISTENTE") RefreshAssistantStatus();' not in timer
    assert 'if(active_view=="RESERVA" || active_view=="ASSISTENTE" || active_view=="UNAVAILABLE") return;' in health
    assert '"REC_REFRESH"' in clear_fields and '"REC_CLOSE"' in clear_fields



def test_native_mt5_navigation_never_routes_unimplemented_modules_to_unrelated_views():
    source = EA.read_text(encoding="utf-8")
    routing = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    health = source.split("void RefreshHealth()", 1)[1].split("void RefreshMarketAssets()", 1)[0]

    # Decision engine has no dedicated native view yet; do not disguise analysis as it.
    assert 'if(module=="Motor de Decisão") return "ANALISE";' not in routing
    assert 'return "UNAVAILABLE";' in routing
    # An unavailable module must not create background health widgets over its notice.
    assert 'if(active_view=="UNAVAILABLE") return;' in health


def test_native_mt5_environment_and_statistics_are_not_misrepresented_as_other_modules():
    source = EA.read_text(encoding="utf-8")
    routing = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    lab = source.split('}else if(active_view=="LAB"){', 1)[1].split('}else if(active_view=="ENSINO"){', 1)[0]

    assert 'if(module=="Ambiente MT5 DEMO / Simulação") return "LAB";' not in routing
    assert 'if(module=="Memória" || module=="Estatísticas") return "MEMORIA";' not in routing
    assert 'if(module=="Memória") return "MEMORIA";' in routing
    assert "Replay: indisponivel nesta interface" in lab
    assert "Replay: disponivel no laboratorio" not in lab
