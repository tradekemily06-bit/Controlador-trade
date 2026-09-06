def passes_filters(
    *,
    market_open: bool,
    data_ok: bool,
    risk_ok: bool,
    score: float,
    confirmed: bool,
) -> bool:
    """Verifica condições mínimas antes de permitir uma decisão."""

    if not market_open:
        return False

    if not data_ok:
        return False

    if not risk_ok:
        return False

    if not confirmed:
        return False

    if not 0 <= score <= 100:
        return False

    if 30 < score < 70:
        return False

    return True
