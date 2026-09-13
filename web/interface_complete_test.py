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
        "/api/analyze",
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
        "REAL continua desabilitado",
    ):
        assert marker in HTML
