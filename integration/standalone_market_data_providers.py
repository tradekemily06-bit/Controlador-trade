"""Explicit opt-in factory for built-in read-only market-data adapters."""
from __future__ import annotations

from typing import Any


def build_configured_market_data_providers(
    provider_id: str | None,
) -> dict[str, tuple[Any, str]]:
    """Build only adapters explicitly selected by trusted server configuration.

    No provider is enabled implicitly. This prevents a default public feed from
    being mistaken for the user's connected broker/account.
    """
    selected = (provider_id or "").strip().lower()
    if not selected:
        return {}
    if selected == "biquote":
        from data.biquote_provider import BiQuoteProvider

        return {"biquote": (BiQuoteProvider(), "biquote_public_ohlc")}
    raise ValueError(f"unsupported standalone market-data provider: {selected}")
