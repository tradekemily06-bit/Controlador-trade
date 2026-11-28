"""Explicit opt-in factory for one or more read-only market-data adapters."""
from __future__ import annotations

from typing import Any


def _build_one(
    provider_id: str, *, ctrader_adapter_factory=None
) -> tuple[Any, str]:
    if provider_id == "biquote":
        from data.biquote_provider import BiQuoteProvider
        return BiQuoteProvider(), "biquote_public_ohlc"
    if provider_id == "mt5_relay":
        import os
        from pathlib import Path
        from integration.mt5_relay_store import MT5RelayStore

        runtime_dir = Path(os.getenv("CONTROLADOR_RUNTIME_DIR", ".runtime-standalone")).resolve()
        expected_source_id = os.getenv("CONTROLADOR_MT5_RELAY_SOURCE_ID", "").strip()
        if not expected_source_id:
            raise RuntimeError("CONTROLADOR_MT5_RELAY_SOURCE_ID precisa ser provisionado para o relay MT5")
        relay = MT5RelayStore(runtime_dir / "mt5-relay.sqlite3", expected_source_id=expected_source_id)
        return relay, "MT5 local relay DEMO read-only"
    if provider_id in {"mt5_demo", "icmarkets_mt5_demo"}:
        from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter
        return ICMarketsMT5DemoMarketDataAdapter(), "IC Markets MT5 DEMO read-only"
    if provider_id == "ctrader_demo":
        if not callable(ctrader_adapter_factory):
            raise RuntimeError(
                "cTrader DEMO requer factory de transporte OAuth/Open API provisionada pelo host"
            )
        from integration.ctrader_readonly_market_data_adapter import CTraderReadOnlyMarketDataAdapter
        adapter = ctrader_adapter_factory()
        if not isinstance(adapter, CTraderReadOnlyMarketDataAdapter):
            raise TypeError("cTrader factory deve retornar CTraderReadOnlyMarketDataAdapter")
        return adapter, "cTrader Open API DEMO read-only"
    raise ValueError(f"unsupported standalone market-data provider: {provider_id}")


def build_configured_market_data_providers(
    provider_id: str | None, *, ctrader_adapter_factory=None
) -> dict[str, tuple[Any, str]]:
    """Build every explicitly configured adapter; never infer a user connection.

    Accepts a comma-separated allowlisted list so several independent feeds can
    be registered at once. The registry still selects one analysis source at a
    time; connection registration is not a claim that sources are fused.
    """
    raw = (provider_id or "").strip().lower()
    if not raw:
        return {}
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    if not requested:
        return {}
    normalized = [
        "mt5_demo" if item == "icmarkets_mt5_demo" else item
        for item in requested
    ]
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate market-data provider configuration")
    return {
        key: _build_one(key, ctrader_adapter_factory=ctrader_adapter_factory)
        for key in normalized
    }
