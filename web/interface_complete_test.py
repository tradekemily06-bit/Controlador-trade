from pathlib import Path


HTML = Path(__file__).with_name("index.html").read_text(encoding="utf-8")


def test_interface_contains_core_modules():
    for marker in (
        "id=\"painel\"",
        "id=\"operacao\"",
        "id=\"analise\"",
        "id=\"laboratorio\"",
        "id=\"memoria\"",
        "id=\"risco\"",
        "id=\"noticias\"",
        "id=\"config\"",
        "id=\"conexoes\"",
    ):
        assert marker in HTML


def test_interface_contains_ecosystem_concepts_and_safety():
    for marker in (
        "Tendência",
        "Estrutura",
        "Suporte / resistência",
        "Topos / fundos",
        "Volume",
        "Rompimento",
        "Pullback",
        "Pavio / rejeição",
        "Retirada de pavio",
        "Vela comando / força",
        "GAB",
        "DDT",
        "Pressão alta / baixa",
        "Taxa dívida",
        "REAL BLOQUEADO",
        "DEMO VALIDADO",
        "FAIL-CLOSED",
        "Kill switch",
        "Reconciliação",
    ):
        assert marker in HTML


def test_interface_wires_existing_safe_apis():
    for marker in (
        "/api/status",
        "/api/runtime/analysis",
        "/api/replay",
        "/api/memory?limit=8",
        "/api/statistics",
        "/api/outcome",
        "/api/risk",
        "/api/news?limit=8",
    ):
        assert marker in HTML


def test_interface_surfaces_critical_runtime_observability():
    for marker in (
        "id=\"runtimeStatus\"",
        "id=\"runtimeHealth\"",
        "id=\"runtimeAlerts\"",
        "status?.health",
        "CRITICAL",
        "WARNING",
        "SAÚDE INDISPONÍVEL",
        "Execução permanece bloqueada",
        "REAL só pode ser executado pelo fluxo controlado",
    ):
        assert marker in HTML


def test_web_close_ui_uses_read_only_reconciliation_and_reports_true_state():
    start = HTML.index("async function closeRuntimeCycle(")
    end = HTML.index("async function runRuntimeCycle()", start)
    close = HTML[start:end]
    assert "/api/runtime/close" in close
    assert "/api/runtime/close/reconcile" in close
    assert "state==='CLOSED'" in close
    assert "state==='OPEN'" in close
    assert "Fechamento inconclusivo" in close
    assert "ciclo foi preservada" in close
