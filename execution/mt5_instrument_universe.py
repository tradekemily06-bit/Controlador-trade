from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class MT5InstrumentStatus:
    """Read-only status for one MT5 instrument."""

    symbol: str
    asset_class: str
    visible: bool
    tradeable: bool
    quote_available: bool
    weekend_capable: bool
    state: str
    reason: str


CRYPTO_KEYWORDS = frozenset(
    {
        "BTC", "ETH", "LTC", "ADA", "SOL", "XRP", "DOGE", "BNB", "DOT",
        "LINK", "XLM", "UNI", "XTZ", "BCH", "DSH", "AVX", "KSM", "GLM",
        "MTC", "XMR", "TRX",
    }
)


def _asset_class(symbol: str) -> str:
    upper = symbol.upper()
    return "crypto" if any(token in upper for token in CRYPTO_KEYWORDS) else "other"


def _has_open_session(mt5: Any, symbol: str, now: datetime) -> bool | None:
    """Return session-open state when the MT5 runtime exposes session data."""
    session_fn = getattr(mt5, "symbol_info_session_trade", None)
    if not callable(session_fn):
        return None

    mt5_day = (now.weekday() + 1) % 7  # MT5: Sunday=0, Monday=1 ... Saturday=6.
    now_seconds = now.hour * 3600 + now.minute * 60 + now.second

    for index in range(32):
        try:
            session = session_fn(symbol, mt5_day, index)
        except Exception:
            return None
        if session is None:
            break
        start = int(getattr(session, "from", 0))
        end = int(getattr(session, "to", 0))
        if start == end:
            return True
        if start <= end and start <= now_seconds <= end:
            return True
        if start > end and (now_seconds >= start or now_seconds <= end):
            return True
    return False


def discover_mt5_instruments(
    mt5: Any,
    *,
    now: datetime | None = None,
    include_invisible: bool = False,
) -> tuple[MT5InstrumentStatus, ...]:
    """Discover the broker's current MT5 symbol universe without trading.

    The broker decides which symbols exist. The function deliberately avoids a
    hard-coded three-asset universe and reports quote/session availability so
    the decision layer can skip closed or unusable instruments.
    """
    symbols = mt5.symbols_get()
    if symbols is None:
        return ()

    current = now or datetime.now(timezone.utc)
    result: list[MT5InstrumentStatus] = []
    disabled_modes = {
        value
        for value in (
            getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", None),
            getattr(mt5, "SYMBOL_TRADE_MODE_CLOSEONLY", None),
        )
        if value is not None
    }

    for item in symbols:
        symbol = str(getattr(item, "name", "")).strip()
        if not symbol:
            continue
        info = mt5.symbol_info(symbol)
        if info is None:
            continue

        visible = bool(getattr(info, "visible", False))
        if not visible and not include_invisible:
            continue

        tick = mt5.symbol_info_tick(symbol)
        quote_available = tick is not None and any(
            getattr(tick, field, 0) for field in ("bid", "ask", "last")
        )
        session_open = _has_open_session(mt5, symbol, current)
        trade_mode = getattr(info, "trade_mode", None)
        disabled = trade_mode in disabled_modes
        tradeable = not disabled and quote_available and session_open is not False

        if session_open is False:
            state, reason = "CLOSED", "sessão de negociação fechada"
        elif disabled:
            state, reason = "DISABLED", "símbolo sem negociação"
        elif not quote_available:
            state, reason = "NO_QUOTE", "cotação indisponível"
        else:
            state, reason = "OPEN", "símbolo disponível para análise"

        asset_class = _asset_class(symbol)
        result.append(
            MT5InstrumentStatus(
                symbol=symbol,
                asset_class=asset_class,
                visible=visible,
                tradeable=tradeable,
                quote_available=quote_available,
                weekend_capable=asset_class == "crypto",
                state=state,
                reason=reason,
            )
        )

    return tuple(sorted(result, key=lambda item: (not item.tradeable, item.symbol)))


def eligible_mt5_instruments(
    statuses: Iterable[MT5InstrumentStatus],
) -> tuple[MT5InstrumentStatus, ...]:
    """Return only instruments currently usable by the analysis pipeline."""
    return tuple(status for status in statuses if status.tradeable)
