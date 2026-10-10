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


def test_interface_contains_calculated_evidence_and_runtime_safety():
    for marker in (
        "Evidência técnica calculada",
        'id="indicatorReadout"',
        "EMA 9/21",
        "RSI 14",
        "MACD",
        "ATR 14",
        "GAB, DDT, pressão e taxa dívida permanecem conceitos contextuais",
        "REAL: BLOQUEADO",
        "MT5 DEMO: VERIFICANDO",
        "FAIL-CLOSED",
        "Kill switch",
        "Reconciliação",
    ):
        assert marker in HTML
    assert '<span class="chip">Tendência</span>' not in HTML
    assert '<span class="chip">DEMO VALIDADO</span>' not in HTML


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
