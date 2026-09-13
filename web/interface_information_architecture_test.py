from pathlib import Path
import re


HTML = Path(__file__).with_name("index.html").read_text(encoding="utf-8")


def test_operational_safety_is_in_the_operational_area():
    operation = HTML.split('id="operacao"', 1)[1].split('<div class="section"', 1)[0]
    assert "Risk Gate" not in operation or "Risco" in HTML
    assert "FAIL-CLOSED" in operation
    assert "Execução: DEMO" in operation
    assert "Auditoria: ativa" in operation


def test_secondary_modules_are_not_promoted_to_technical_top_level_items():
    nav_match = re.search(r'<nav class="nav">(.*?)</nav>', HTML, re.S)
    assert nav_match, "primary mobile navigation is missing"
    nav = nav_match.group(1)

    # Technical concepts are knowledge, not navigation destinations.
    for concept in (
        "Tendência",
        "Estrutura",
        "Suporte",
        "Topos",
        "Volume",
        "Rompimento",
        "Pullback",
        "Pavio",
        "DDT",
        "GAB",
        "Taxa dívida",
    ):
        assert concept not in nav

    # Learning/review is kept together rather than split into many top-level items.
    assert 'href="#laboratorio"' in nav
    assert 'href="#memoria"' in nav


def test_critical_and_admin_destinations_have_distinct_roles():
    nav = re.search(r'<nav class="nav">(.*?)</nav>', HTML, re.S).group(1)

    # Risk is operationally critical and remains visible in the page itself.
    assert 'id="risco"' in HTML
    assert "Kill switch" in HTML
    assert "Reconciliação" in HTML

    # Detailed connections/security are administration, not a primary trading command.
    assert 'id="conexoes"' in HTML
    assert "Conexões & Segurança" in HTML


def test_real_execution_has_no_interface_enablement_path():
    assert "REAL BLOQUEADO" in HTML
    assert "REAL /" not in HTML
    assert "DESABILITADO" in HTML
