from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
import math
from typing import Any, Callable

from core.operational_state import OperationalState


class MT5RiskStateProviderError(RuntimeError):
    """Raised when authoritative MT5 DEMO risk state cannot be established."""


@dataclass(frozen=True)
class MT5DemoRiskStateConfig:
    """Explicit broker-edge configuration for authoritative DEMO state."""

    symbol: str | None = None
    timeframe: int | None = None


class MT5DemoRiskStateProvider:
    """Read authoritative operational risk state directly from an MT5 DEMO terminal.

    This class is deliberately broker-specific and remains outside the core risk
    policy. It never invents missing values: unsupported or unavailable fields are
    returned as UNKNOWN, while failures to obtain required account/history data
    raise so the execution gateway can fail closed.

    ``last_processed_candle`` is intentionally left UNKNOWN here. MT5 can expose
    the latest available market candle, but it cannot prove which candle the
    Controlador strategy actually processed. Treating the latest available bar
    as a processed bar would create a false authority claim in the risk identity.
    """

    def __init__(
        self,
        config: MT5DemoRiskStateConfig | None = None,
        *,
        mt5_module: Any = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or MT5DemoRiskStateConfig()
        self._mt5 = mt5_module
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5RiskStateProviderError("MetaTrader5 não instalado") from exc
            self._mt5 = mt5
        return self._mt5

    def current_risk_state(self) -> OperationalState:
        mt5 = self._module()
        if not mt5.initialize():
            raise MT5RiskStateProviderError("MT5 não inicializou")
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5RiskStateProviderError("conta MT5 não confirmada como DEMO")

            positions = mt5.positions_get()
            if positions is None:
                raise MT5RiskStateProviderError("posições MT5 indisponíveis")

            now = self._utc_now()
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            deals = mt5.history_deals_get(start, now)
            if deals is None:
                raise MT5RiskStateProviderError("histórico de transações MT5 indisponível")

            balance = self._number(account, "balance")
            equity = self._number(account, "equity")
            unrealized = self._number(account, "profit")

            scoped_positions = self._scope_positions(positions)
            return OperationalState(
                balance=balance,
                equity=equity,
                realized_pnl=self._realized_pnl(deals, mt5),
                unrealized_pnl=unrealized,
                trades_today=self._trades_today(deals, mt5),
                consecutive_losses=self._consecutive_losses(deals, mt5),
                open_positions=len(scoped_positions),
                net_position=self._net_position(scoped_positions, mt5),
                exposure=self._exposure(scoped_positions, mt5),
                market_open=self._market_open(mt5),
                last_processed_candle=None,
            )
        except MT5RiskStateProviderError:
            raise
        except Exception as exc:
            raise MT5RiskStateProviderError(
                f"falha ao ler estado de risco MT5: {type(exc).__name__}"
            ) from exc
        finally:
            try:
                mt5.shutdown()
            except Exception:
                pass

    def _utc_now(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime):
            raise MT5RiskStateProviderError("clock returned invalid datetime")
        if value.tzinfo is None:
            raise MT5RiskStateProviderError("clock datetime must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _is_demo_account(account: Any, mt5: Any) -> bool:
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        return demo_mode is not None and getattr(account, "trade_mode", None) == demo_mode

    @staticmethod
    def _number(account: Any, field: str) -> float:
        value = getattr(account, field, None)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise MT5RiskStateProviderError(f"account.{field} inválido")
        return float(value)

    def _scope_positions(self, positions: Any) -> tuple[Any, ...]:
        if self.config.symbol is None:
            return tuple(positions)
        wanted = self.config.symbol.strip()
        if not wanted:
            raise MT5RiskStateProviderError("symbol inválido")
        return tuple(position for position in positions if getattr(position, "symbol", None) == wanted)

    @staticmethod
    def _net_position(positions: tuple[Any, ...], mt5: Any) -> float | None:
        buy = getattr(mt5, "POSITION_TYPE_BUY", 0)
        sell = getattr(mt5, "POSITION_TYPE_SELL", 1)
        total = 0.0
        for position in positions:
            volume = getattr(position, "volume", None)
            kind = getattr(position, "type", None)
            if not isinstance(volume, (int, float)) or not math.isfinite(float(volume)) or volume < 0:
                return None
            if kind == buy:
                total += float(volume)
            elif kind == sell:
                total -= float(volume)
            else:
                return None
        return total

    @staticmethod
    def _exposure(positions: tuple[Any, ...], mt5: Any) -> float | None:
        """Aggregate current price-notional exposure where symbol metadata supports it."""
        total = 0.0
        for position in positions:
            volume = getattr(position, "volume", None)
            price = getattr(position, "price_current", None)
            symbol = getattr(position, "symbol", None)
            if not isinstance(volume, (int, float)) or not isinstance(price, (int, float)):
                return None
            if not math.isfinite(float(volume)) or not math.isfinite(float(price)) or volume < 0 or price < 0:
                return None
            info = mt5.symbol_info(symbol) if symbol else None
            contract = getattr(info, "trade_contract_size", None) if info is not None else None
            if not isinstance(contract, (int, float)) or not math.isfinite(float(contract)) or contract <= 0:
                return None
            total += abs(float(volume) * float(price) * float(contract))
        return total

    @staticmethod
    def _is_entry(deal: Any, mt5: Any) -> bool:
        entry = getattr(deal, "entry", None)
        return entry in {
            getattr(mt5, "DEAL_ENTRY_IN", 0),
            getattr(mt5, "DEAL_ENTRY_INOUT", 2),
        }

    @staticmethod
    def _is_exit(deal: Any, mt5: Any) -> bool:
        entry = getattr(deal, "entry", None)
        return entry in {
            getattr(mt5, "DEAL_ENTRY_OUT", 1),
            getattr(mt5, "DEAL_ENTRY_OUT_BY", 3),
            getattr(mt5, "DEAL_ENTRY_INOUT", 2),
        }

    @staticmethod
    def _deal_net(deal: Any) -> float | None:
        total = 0.0
        for field in ("profit", "swap", "commission", "fee"):
            value = getattr(deal, field, 0.0)
            if value is None:
                value = 0.0
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                return None
            total += float(value)
        return total

    @classmethod
    def _trades_today(cls, deals: Any, mt5: Any) -> int | None:
        return sum(1 for deal in deals if cls._is_entry(deal, mt5))

    @classmethod
    def _consecutive_losses(cls, deals: Any, mt5: Any) -> int | None:
        exits = [deal for deal in deals if cls._is_exit(deal, mt5)]
        exits.sort(key=lambda deal: (getattr(deal, "time_msc", 0), getattr(deal, "time", 0)))
        streak = 0
        for deal in reversed(exits):
            result = cls._deal_net(deal)
            if result is None:
                return None
            if result < 0:
                streak += 1
            else:
                break
        return streak

    @classmethod
    def _realized_pnl(cls, deals: Any, mt5: Any) -> float | None:
        total = 0.0
        for deal in deals:
            if cls._is_exit(deal, mt5):
                result = cls._deal_net(deal)
                if result is None:
                    return None
                total += result
        return total

    def _market_open(self, mt5: Any) -> bool | None:
        symbol = self.config.symbol
        if not symbol or not hasattr(mt5, "symbol_info_tick"):
            return None
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False
        bid = getattr(tick, "bid", None)
        ask = getattr(tick, "ask", None)
        if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) and value > 0 for value in (bid, ask)):
            return False
        return True

    def _last_candle(self, mt5: Any) -> datetime | None:
        """Never equate an available MT5 bar with a strategy-processed bar.

        The authoritative processed-candle marker must come from the strategy
        runtime itself. Until that source is connected, UNKNOWN is safer than
        fabricating processing state from market-data availability.
        """
        return None
