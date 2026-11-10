from __future__ import annotations

from typing import Any


def closed_panel_signal(result: Any) -> tuple[str, str, str]:
    """Return a validated last-session signal, score label, and display color."""
    if not isinstance(result, dict):
        return "INDISPONÍVEL", "—", "#7F8B97"
    raw_signal = str(result.get("signal") or "").strip().upper()
    signals = {
        "BUY": ("↑ COMPRAR", "#46D6AD"),
        "COMPRAR": ("↑ COMPRAR", "#46D6AD"),
        "SELL": ("↓ VENDER", "#FF667A"),
        "VENDER": ("↓ VENDER", "#FF667A"),
        "WAIT": ("AGUARDAR", "#E8C66A"),
        "AGUARDAR": ("AGUARDAR", "#E8C66A"),
    }
    if raw_signal not in signals:
        return "INDISPONÍVEL", "—", "#7F8B97"
    analysis = result.get("analysis")
    score = analysis.get("score") if isinstance(analysis, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 1 <= score <= 100:
        return "INDISPONÍVEL", "—", "#7F8B97"
    # Normalize once so the displayed integer and its strength band can
    # never disagree for fractional provider scores.
    normalized_score = int(score)
    strength = (
        "FRACA" if normalized_score <= 69
        else "MODERADA" if normalized_score <= 79
        else "FORTE"
    )
    signal_label, color = signals[raw_signal]
    return signal_label, f"{normalized_score}% · {strength}", color
