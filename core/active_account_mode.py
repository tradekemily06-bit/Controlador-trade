"""Fail-closed resolver for the single active broker account mode."""
from __future__ import annotations

from typing import Any


VALID_ACCOUNT_MODES = frozenset({"DEMO", "REAL"})


def resolve_active_account_mode(adapter: Any | None) -> dict[str, Any]:
    """Return exactly one verified mode, or unavailable; never infer or show both."""
    if adapter is None:
        return {
            "status": "UNAVAILABLE",
            "mode": None,
            "reason": "Nenhuma conexão de conta forneceu o modo ativo.",
        }
    getter = getattr(adapter, "get_account_mode", None)
    if not callable(getter):
        return {
            "status": "UNAVAILABLE",
            "mode": None,
            "reason": "O adaptador não informa o modo da conta.",
        }
    try:
        mode = getter()
    except Exception:
        return {
            "status": "UNAVAILABLE",
            "mode": None,
            "reason": "Não foi possível verificar o modo da conta conectada.",
        }
    if not isinstance(mode, str) or mode.strip().upper() not in VALID_ACCOUNT_MODES:
        return {
            "status": "UNAVAILABLE",
            "mode": None,
            "reason": "O modo retornado pela conexão é inválido ou não identificado.",
        }
    return {
        "status": "CONNECTED",
        "mode": mode.strip().upper(),
        "reason": None,
    }
