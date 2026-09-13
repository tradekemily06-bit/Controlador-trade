from __future__ import annotations

import ast
from pathlib import Path


CORE_DIR = Path(__file__).resolve().parent / "core"

# Concrete vendors/infrastructure packages must never become a hard dependency
# of the decision core. Integrations belong outside core/ and must be optional.
FORBIDDEN_TOP_LEVEL_MODULES = {
    "MetaTrader5",
    "ccxt",
    "yfinance",
    "stripe",
    "boto3",
    "redis",
    "sqlalchemy",
}


def _imported_top_levels(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", 1)[0])
    return modules


def test_core_does_not_import_concrete_external_providers() -> None:
    violations: list[str] = []
    for path in sorted(CORE_DIR.glob("*.py")):
        imported = _imported_top_levels(path.read_text(encoding="utf-8"))
        forbidden = sorted(imported & FORBIDDEN_TOP_LEVEL_MODULES)
        if forbidden:
            violations.append(f"{path.relative_to(CORE_DIR.parent)}: {', '.join(forbidden)}")

    assert not violations, (
        "Dependência externa concreta encontrada no núcleo; "
        "mova a integração para uma camada externa/adaptador: "
        + "; ".join(violations)
    )
