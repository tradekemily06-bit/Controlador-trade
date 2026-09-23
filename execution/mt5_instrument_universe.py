from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from execution.mt5_session import coordinator_for


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


def _path_and_description(info: Any) -> str:
    return " ".join(
        str(getattr(info, field, "") or "")
        for field in ("path", "description", "name")
    ).upper()


def _asset_class(mt5: Any, symbol: str, info: Any) -> str:
    """Classify from broker metadata first, with conservative fallbacks.

    The broker's own symbol metadata is authoritative when it exposes a
    calculation mode/path. Symbol-name heuristics are only a fallback and
    never create a tradeable instrument by themselves.
    """
    text = _path_and_description(info)
    upper = symbol.upper()

    path_tokens = (
        ("crypto", ("CRYPTO", "CRYPT", "DIGITAL ASSET")),
        ("forex", ("FOREX", "FX", "CURRENCIES")),
        ("index", ("INDEX", "INDICES", "INDICE")),
        ("stock", ("STOCK", "SHARES", "EQUITIES", "EQUITY")),
        ("bond", ("BOND", "BONDS", "FIXED INCOME")),
        ("futures", ("FUTURE", "FUTURES")),
        ("commodity", ("COMMOD", "METAL", "ENERGY", "OIL", "GAS", "GOLD", "SILVER")),
    )
    for asset_class, tokens in path_tokens:
        if any(token in text for token in tokens):
            return asset_class

    calc_mode = getattr(info, "trade_calc_mode", None)
    calc_map = {
        getattr(mt5, "SYMBOL_CALC_MODE_FOREX", object()): "forex",
        getattr(mt5, "SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE", object()): "forex",
        getattr(mt5, "SYMBOL_CALC_MODE_FUTURES", object()): "futures",
        getattr(mt5, "SYMBOL_CALC_MODE_CFDINDEX", object()): "index",
        getattr(mt5, "SYMBOL_CALC_MODE_EXCH_STOCKS", object()): "stock",
        getattr(mt5, "SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX", object()): "stock",
        getattr(mt5, "SYMBOL_CALC_MODE_CFD_BONDS", object()): "bond",
        getattr(mt5, "SYMBOL_CALC_MODE_EXCH_BONDS", object()): "bond",
        getattr(mt5, "SYMBOL_CALC_MODE_EXCH_FUTURES", object()): "futures",
        getattr(mt5, "SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS", object()): "futures",
    }
    if calc_mode in calc_map:
        return calc_map[calc_mode]

    if any(token in text for token in CRYPTO_KEYWORDS) or any(token in upper for token in CRYPTO_KEYWORDS):
        return "crypto"

    if any(token in upper for token in ("XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "NGAS")):
        return "commodity"

    # A conservative fallback keeps the universe complete without pretending
    # to know an instrument's class when broker metadata is insufficient.
    return "other"


def _has_open_session(mt5: Any, symbol: str, now: datetime) -> bool | None:
    """Return session-open state when the MT5 runtime exposes session data."""
    session_fn = getattr(mt5, "symbol_info_session_trade", None)
    if not callable(session_fn):
        return None

    mt5_day = (now.weekday() + 1) % 7
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


def _has_weekend_session(mt5: Any, symbol: str) -> bool | None:
    """Detect whether the broker exposes a Saturday or Sunday trade session."""
    session_fn = getattr(mt5, "symbol_info_session_trade", None)
    if not callable(session_fn):
        return None

    for mt5_day in (0, 6):  # Sunday and Saturday in MT5 convention.
        for index in range(32):
            try:
                session = session_fn(symbol, mt5_day, index)
            except Exception:
                return None
            if session is None:
                break
            return True
    return False


def discover_mt5_instruments(
    mt5: Any,
    *,
    now: datetime | None = None,
    include_invisible: bool = False,
) -> tuple[MT5InstrumentStatus, ...]:
    """Discover the broker's current MT5 symbol universe without trading.

    The discovery boundary owns a DEMO MT5 session lease for its complete
    read-only scan. Callers may already hold another owner; the coordinator
    reference-counts the nested ownership and prevents premature shutdown.
    """
    owner = f"instrument-universe:{id(mt5)}"
    coordinator = coordinator_for(mt5)
    if not coordinator.acquire(mt5, mode="DEMO", owner=owner):
        raise RuntimeError("MT5 DEMO ocupado por outra sessão; descoberta bloqueada.")
    try:
        with coordinator.operation(mt5, mode="DEMO", owner=owner):
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
                disabled = getattr(info, "trade_mode", None) in disabled_modes
                tradeable = not disabled and quote_available and session_open is not False

                if session_open is False:
                    state, reason = "CLOSED", "sessão de negociação fechada"
                elif disabled:
                    state, reason = "DISABLED", "símbolo sem negociação"
                elif not quote_available:
                    state, reason = "NO_QUOTE", "cotação indisponível"
                else:
                    state, reason = "OPEN", "símbolo disponível para análise"

                asset_class = _asset_class(mt5, symbol, info)
                weekend_session = _has_weekend_session(mt5, symbol)
                weekend_capable = (
                    weekend_session
                    if weekend_session is not None
                    else asset_class == "crypto"
                )
                result.append(
                    MT5InstrumentStatus(
                        symbol=symbol,
                        asset_class=asset_class,
                        visible=visible,
                        tradeable=tradeable,
                        quote_available=quote_available,
                        weekend_capable=weekend_capable,
                        state=state,
                        reason=reason,
                    )
                )

            return tuple(sorted(result, key=lambda item: (not item.tradeable, item.symbol)))
    finally:
        coordinator.release(mt5, owner=owner)


def eligible_mt5_instruments(
    statuses: Iterable[MT5InstrumentStatus],
) -> tuple[MT5InstrumentStatus, ...]:
    """Return only instruments currently usable by the analysis pipeline."""
    return tuple(status for status in statuses if status.tradeable)
