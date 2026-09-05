def passes_filters(*, market_open: bool, data_ok: bool, risk_ok: bool) -> bool:
    """Filtro de segurança antes de permitir uma decisão operacional."""
    return market_open and data_ok and risk_ok
