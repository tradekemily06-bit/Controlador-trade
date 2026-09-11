from pathlib import Path


def test_web_shell_exposes_outcome_controls():
    html = Path("web/index.html").read_text(encoding="utf-8")
    for marker in (
        "Resultado da operação",
        "/api/outcome",
        'data-outcome="WIN"',
        'data-outcome="LOSS"',
        'data-outcome="DRAW"',
        'data-outcome="OPEN"',
        'data-outcome="VOID"',
    ):
        assert marker in html
