from __future__ import annotations

from typing import Any, Iterable

from core.senior_asset_suitability import AssetSuitabilityObservation, SeniorAssetAssessment, prioritize_assets
from execution.mt5_instrument_universe import MT5InstrumentStatus


def _tick_evidence(mt5: Any, symbol: str) -> tuple[float | None, bool | None, bool | None]:
    """Read observable quote evidence without inventing freshness thresholds."""
    try:
        tick = mt5.symbol_info_tick(symbol)
    except Exception:
        return None, None, None
    if tick is None:
        return None, None, None

    bid = getattr(tick, "bid", None)
    ask = getattr(tick, "ask", None)
    spread = None
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and ask >= bid and ask > 0:
        spread = float(ask - bid)

    timestamp = getattr(tick, "time_msc", None) or getattr(tick, "time", None)
    timestamped = isinstance(timestamp, (int, float)) and timestamp > 0

    volume = getattr(tick, "volume_real", None)
    if not isinstance(volume, (int, float)) or volume <= 0:
        volume = getattr(tick, "volume", None)
    liquidity_observed = bool(isinstance(volume, (int, float)) and volume > 0)

    return spread, liquidity_observed, bool(timestamped)


def build_asset_suitability_observations(
    mt5: Any,
    statuses: Iterable[MT5InstrumentStatus],
) -> tuple[AssetSuitabilityObservation, ...]:
    """Translate broker observations into the senior suitability boundary.

    The bridge deliberately records timestamp presence rather than claiming a
    quote is fresh. A freshness threshold must come from the broker/data-quality
    contract instead of being silently invented here.
    """
    observations: list[AssetSuitabilityObservation] = []
    for status in statuses:
        spread, liquidity, timestamped = _tick_evidence(mt5, status.symbol)
        if status.state == "OPEN":
            session_open: bool | None = True
        elif status.state == "CLOSED":
            session_open = False
        else:
            session_open = None
        observations.append(
            AssetSuitabilityObservation(
                symbol=status.symbol,
                asset_class=status.asset_class,
                tradeable=status.tradeable,
                quote_available=status.quote_available,
                session_open=session_open,
                weekend_capable=status.weekend_capable,
                quote_fresh=timestamped if timestamped else None,
                spread_observed=spread,
                liquidity_observed=liquidity,
                data_quality_ok=status.quote_available,
                domain_expertise_available=True,
            )
        )
    return tuple(observations)


def prioritize_mt5_assets(
    mt5: Any,
    statuses: Iterable[MT5InstrumentStatus],
) -> tuple[SeniorAssetAssessment, ...]:
    """Prioritize the complete observed broker universe for analysis attention."""
    return prioritize_assets(build_asset_suitability_observations(mt5, statuses))
