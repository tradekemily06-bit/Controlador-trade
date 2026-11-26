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
    if selected == "mt5_relay":
        import os
        from pathlib import Path
        from integration.mt5_relay_store import MT5RelayStore

        runtime_dir = Path(os.getenv("CONTROLADOR_RUNTIME_DIR", ".runtime-standalone")).resolve()
        relay = MT5RelayStore(runtime_dir / "mt5-relay.sqlite3")
        return {"mt5_relay": (relay, "MT5 local relay DEMO read-only")}
    if selected in {"mt5_demo", "icmarkets_mt5_demo"}:
        from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter

        return {
            "mt5_demo": (
                ICMarketsMT5DemoMarketDataAdapter(),
                "IC Markets MT5 DEMO read-only",
            )
        }
    raise ValueError(f"unsupported standalone market-data provider: {selected}")
