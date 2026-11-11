import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL_DIR = ROOT / "streamlit_panel"
EA_PATH = ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5"


def test_streamlit_and_native_mt5_share_the_six_area_and_module_contract():
    reference = json.loads(
        (PANEL_DIR / "controlador_trader_referencia_visual.json").read_text(encoding="utf-8")
    )["open_state"]["tabs"]
    streamlit = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    native = EA_PATH.read_text(encoding="utf-8")

    expected_areas = [
        "COCKPIT",
        "ANÁLISE",
        "ESTUDO",
        "RESERVA FISCAL",
        "ASSISTENTE DO ECOSSISTEMA",
        "CENTRAL",
    ]
    assert 'AREAS["RESERVA FISCAL"] = ["Reserva Fiscal"]' in streamlit
    assert 'AREAS["ASSISTENTE DO ECOSSISTEMA"] = ["Assistente do Ecossistema"]' in streamlit
    assert 'AREAS["CENTRAL"] = ["Financeiro", *_REFERENCE_TABS["MAIS / ADMIN"][1:]]' in streamlit
    area_definition = streamlit.split("AREAS = {", 1)[1].split('if "panel_open"', 1)[0]
    assert 'for name in ("COCKPIT", "ANÁLISE", "ESTUDO")' in area_definition
    assert expected_areas[-1] == "CENTRAL"

    native_labels = 'string area_labels[6]={"COCKPIT","ANÁLISE","ESTUDO","FISCAL","ASSIST.","CENTRAL"};'
    assert native_labels in native
    module_names = native.split("string AreaModuleName(", 1)[1].split("string AreaModuleLabel(", 1)[0]
    routing = native.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]

    # The reference calls this module "MT5 DEMO / Simulação"; the active
    # product label clarifies that it is the operational environment, not the
    # historical Simulador module under ESTUDO.
    expected_modules = {
        "COCKPIT": ["Operação", "Motor de Decisão", "Gestão de Risco", "Notificações", "Ambiente MT5 DEMO", "Kill Switch"],
        "ANÁLISE": list(reference["ANÁLISE"]),
        "ESTUDO": list(reference["ESTUDO"]),
        "CENTRAL": ["Financeiro", *reference["MAIS / ADMIN"][1:]],
    }
    for modules in expected_modules.values():
        for module in modules:
            native_name = "Ambiente MT5 DEMO / Simulação" if module == "Ambiente MT5 DEMO" else module
            assert f'return "{native_name}";' in module_names, f"native module missing: {module}"

    assert 'else if(area=="RESERVA FISCAL") return "Reserva Fiscal";' in module_names
    assert 'else if(area=="ASSISTENTE DO ECOSSISTEMA") return "Assistente do Ecossistema";' in module_names

    for module, view in {
        "Operação": "COCKPIT",
        "Motor de Decisão": "DECISION",
        "Gestão de Risco": "RISK",
        "Notificações": "NOTIF",
        "Ambiente MT5 DEMO / Simulação": "ENVIRONMENT",
        "Kill Switch": "KILL_SWITCH",
        "Análise de Mercado": "ANALISE",
        "Memória": "MEMORIA",
        "Estatísticas": "STATS",
        "Relatórios": "REPORTS",
        "Laboratório": "LAB",
        "Replay": "REPLAY",
        "Simulador": "SIMULATOR",
        "Descobertas": "DISCOVERIES",
        "Financeiro": "FINANCE",
        "Configurações": "CONFIG",
        "Auditoria": "AUDIT",
        "Segurança": "SECURITY",
        "Conexões": "CONNECTIONS",
        "Multi-Broker": "CONNECTIONS",
    }.items():
        assert f'if(module=="{module}") return "{view}";' in routing, f"native route mismatch: {module}"

    assert 'if(module=="Aprendizado") return "ENSINO";' in routing
    assert 'if(module=="Escola / Tutorial / Onboarding") return "ONBOARDING";' in routing
    assert 'Http("GET","/api/onboarding","",response,code)' in native
    assert 'string guide_json=JsonRawObject(response,"guide");' in native
    assert 'ExtractJsonArrayObjects(guide_json,"steps",objects)' in native
    assert 'authorized!="false"' in native
    api_source = (ROOT / "app.py").read_text(encoding="utf-8")
    onboarding_route = api_source.split('if path == "/api/onboarding" and method == "GET":', 1)[1].split('if path == "/api/preferences" and method == "GET":', 1)[0]
    assert '{"guide": {' in onboarding_route
    assert '"steps": [{ "step_id": step.step_id' in onboarding_route
    assert 'execution_authorized": guide.execution_authorized' in onboarding_route
    assert 'else if(area=="RESERVA FISCAL") return "RESERVA";' in routing
    assert 'else if(area=="ASSISTENTE DO ECOSSISTEMA") return "ASSISTENTE";' in routing
    assert 'return "UNAVAILABLE";' in routing
