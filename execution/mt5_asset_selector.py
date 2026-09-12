from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .mt5_instrument_universe import MT5InstrumentStatus


@dataclass(frozen=True)
class MT5AssetCandidate:
    """Read-only candidate selected from the currently eligible MT5 universe."""

    symbol: str
    asset_class: str
    weekend_capable: bool
    rank: int


def rank_mt5_assets(
    statuses: Iterable[MT5InstrumentStatus],
    *,
    limit: int | None = None,
) -> tuple[MT5AssetCandidate, ...]:
    """Rank currently usable instruments without placing or modifying orders.

    Weekend-capable crypto instruments are preferred when otherwise equally
    eligible. The broker's actual session/quote state remains authoritative.
    """
    eligible = [status for status in statuses if status.tradeable and status.quote_available]
    ordered = sorted(
        eligible,
        key=lambda status: (
            not status.weekend_capable,
            status.asset_class != "crypto",
            status.symbol,
        ),
    )
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        ordered = ordered[:limit]

    return tuple(
        MT5AssetCandidate(
            symbol=status.symbol,
            asset_class=status.asset_class,
            weekend_capable=status.weekend_capable,
            rank=index,
        )
        for index, status in enumerate(ordered, start=1)
    )
