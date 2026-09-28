from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from core.operation_lineage import OperationLineage, OperationLineageStore
from core.p49_outcome_reconciliation import ExternalOutcomeObservation


class MT5OutcomeBridgeError(RuntimeError):
    """Raised when MT5 cannot safely establish factual close/result evidence."""


@dataclass(frozen=True)
class MT5OutcomeEvidence:
    decision_id: str
    cycle_id: str
    request_id: str
    external_container_id: str
    external_close_id: str
    external_result_ids: tuple[str, ...]
    financial_result: float
    outcome: Literal["WIN", "LOSS", "DRAW"]
    observed_at: datetime

    def as_observation(self) -> ExternalOutcomeObservation:
        return ExternalOutcomeObservation(
            cycle_id=self.cycle_id,
            outcome=self.outcome,
            financial_result=self.financial_result,
            source="MT5_DEMO",
            external_reference=self.external_close_id,
            external_container_id=self.external_container_id,
            external_result_ids=self.external_result_ids,
            observed_at=self.observed_at,
        )


@dataclass(frozen=True)
class MT5CloseResult:
    request_id: str
    external_container_id: str
    external_close_id: str | None
    position_closed: bool
    outcome_evidence: MT5OutcomeEvidence | None
    message: str


class ICMarketsMT5DemoOutcomeBridge:
    """DEMO-only close + factual result bridge.

    It never derives a result from order_send(). A financial result exists only
    after MT5 confirms the position is no longer open and exit deals are found
    in history for that exact position.
    """

    _EXIT_ENTRIES = ("DEAL_ENTRY_OUT", "DEAL_ENTRY_INOUT", "DEAL_ENTRY_OUT_BY")

    def __init__(
        self,
        *,
        lineage: OperationLineageStore,
        mt5_module: Any = None,
        magic: int = 2609001,
        deviation: int = 20,
    ) -> None:
        if lineage is None:
            raise ValueError("lineage é obrigatório.")
        if not isinstance(magic, int) or isinstance(magic, bool) or magic <= 0:
            raise ValueError("magic inválido.")
        if not isinstance(deviation, int) or isinstance(deviation, bool) or deviation < 0:
            raise ValueError("deviation inválido.")
        self.lineage = lineage
        self._mt5 = mt5_module
        self.magic = magic
        self.deviation = deviation

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5OutcomeBridgeError(
                    "MetaTrader5 não instalado; o bridge precisa de um terminal MT5 DEMO."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def close_and_observe(self, request_id: str, *, now: datetime | None = None) -> MT5CloseResult:
        lineage = self.lineage.get(request_id)
        if lineage is None:
            raise ValueError("request_id sem linhagem persistida.")
        event_time = now or datetime.now(timezone.utc)
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            raise ValueError("now precisa ser timezone-aware.")

        mt5 = self._module()
        if not mt5.initialize():
            raise MT5OutcomeBridgeError(f"MT5 indisponível: {self._last_error(mt5)}")

        try:
            self._require_demo(mt5)
            external_container_id = lineage.external_container_id or self._resolve_external_container_id(mt5, lineage.external_id)
            if not external_container_id:
                raise MT5OutcomeBridgeError(
                    "não foi possível resolver external_container_id a partir do external_id; resultado permanece UNKNOWN."
                )
            if lineage.external_container_id != external_container_id:
                lineage = self.lineage.attach_external_container_id(request_id, external_container_id, updated_at=event_time)

            position = self._get_single_position(mt5, external_container_id)
            if position is None:
                evidence = self._observe_closed_position(mt5, lineage, event_time)
                if evidence is None:
                    return MT5CloseResult(
                        request_id, external_container_id, lineage.external_close_id, False, None,
                        "posição já não está aberta, mas os deals de saída ainda não foram confirmados.",
                    )
                return MT5CloseResult(
                    request_id, external_container_id, lineage.external_close_id, True, evidence,
                    "posição já estava fechada; resultado financeiro confirmado por deals.",
                )

            if getattr(position, "magic", None) != self.magic:
                raise MT5OutcomeBridgeError(
                    "posição não pertence ao magic do ControladorTrading DEMO; fechamento bloqueado."
                )

            symbol = getattr(position, "symbol", None)
            volume = getattr(position, "volume", None)
            position_type = getattr(position, "type", None)
            if not isinstance(symbol, str) or not symbol.strip():
                raise MT5OutcomeBridgeError("posição sem símbolo válido.")
            if not isinstance(volume, (int, float)) or volume <= 0:
                raise MT5OutcomeBridgeError("posição sem volume válido.")

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise MT5OutcomeBridgeError(f"cotação indisponível para fechamento de {symbol}.")

            buy_type = getattr(mt5, "ORDER_TYPE_BUY", None)
            sell_type = getattr(mt5, "ORDER_TYPE_SELL", None)
            if position_type == buy_type:
                close_type = sell_type
                price = getattr(tick, "bid", None)
            elif position_type == sell_type:
                close_type = buy_type
                price = getattr(tick, "ask", None)
            else:
                raise MT5OutcomeBridgeError("tipo de posição MT5 não reconhecido.")

            if close_type is None or not isinstance(price, (int, float)) or price <= 0:
                raise MT5OutcomeBridgeError("lado/preço de fechamento inválido.")

            filling = getattr(mt5, "ORDER_FILLING_IOC", getattr(mt5, "ORDER_FILLING_RETURN", None))
            payload = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(volume),
                "type": close_type,
                "price": float(price),
                "deviation": self.deviation,
                "magic": self.magic,
                "comment": "ControladorTrading-DEMO-CLOSE",
                "position": int(external_container_id),
                "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
                "type_filling": filling,
            }

            check = mt5.order_check(payload)
            if check is None or getattr(check, "retcode", 0) != 0:
                raise MT5OutcomeBridgeError(f"order_check bloqueou o fechamento: {check}")

            result = mt5.order_send(payload)
            if result is None:
                raise MT5OutcomeBridgeError(
                    f"order_send do fechamento sem confirmação: {self._last_error(mt5)}"
                )

            done_codes = {
                value for value in (
                    getattr(mt5, "TRADE_RETCODE_DONE", None),
                    getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", None),
                ) if value is not None
            }
            if getattr(result, "retcode", None) not in done_codes:
                raise MT5OutcomeBridgeError(
                    f"fechamento rejeitado pelo MT5: retcode={getattr(result, 'retcode', None)}"
                )

            external_close_id = getattr(result, "order", None) or getattr(result, "deal", None)
            if external_close_id is None:
                raise MT5OutcomeBridgeError(
                    "fechamento aceito sem order/deal identificável; resultado permanece UNKNOWN."
                )
            lineage = self.lineage.attach_external_close_id(
                request_id, str(external_close_id), updated_at=event_time
            )

            remaining = self._get_single_position(mt5, external_container_id)
            if remaining is not None:
                return MT5CloseResult(
                    request_id, external_container_id, str(external_close_id), False, None,
                    "fechamento parcial/posição ainda aberta; resultado financeiro não foi fechado.",
                )

            evidence = self._observe_closed_position(mt5, lineage, event_time)
            if evidence is None:
                return MT5CloseResult(
                    request_id, external_container_id, str(external_close_id), True, None,
                    "posição fechada, mas deals de saída ainda não foram confirmados; resultado permanece UNKNOWN.",
                )

            return MT5CloseResult(
                request_id, external_container_id, str(external_close_id), True, evidence,
                "posição fechada e resultado financeiro confirmado por deals MT5.",
            )
        finally:
            try:
                mt5.shutdown()
            except Exception:
                pass

    def observe_closed_position(self, request_id: str, *, now: datetime | None = None) -> MT5OutcomeEvidence | None:
        lineage = self.lineage.get(request_id)
        if lineage is None:
            raise ValueError("request_id sem linhagem persistida.")
        if not lineage.external_container_id:
            raise ValueError("external_container_id ainda não foi resolvido.")
        event_time = now or datetime.now(timezone.utc)
        mt5 = self._module()
        if not mt5.initialize():
            raise MT5OutcomeBridgeError(f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            self._require_demo(mt5)
            if self._get_single_position(mt5, lineage.external_container_id) is not None:
                return None
            return self._observe_closed_position(mt5, lineage, event_time)
        finally:
            try:
                mt5.shutdown()
            except Exception:
                pass

    def _observe_closed_position(
        self,
        mt5: Any,
        lineage: OperationLineage,
        observed_at: datetime,
    ) -> MT5OutcomeEvidence | None:
        deals = mt5.history_deals_get(position=int(lineage.external_container_id))
        if deals is None:
            return None

        exit_deals = []
        for deal in deals:
            entry = getattr(deal, "entry", None)
            if entry in self._entry_constants(mt5):
                ticket = getattr(deal, "ticket", None)
                if ticket is not None:
                    exit_deals.append(deal)

        if not exit_deals:
            return None

        def deal_key(deal: Any) -> tuple[int, int]:
            return (
                int(getattr(deal, "time_msc", getattr(deal, "time", 0)) or 0),
                int(getattr(deal, "ticket", 0) or 0),
            )

        exit_deals.sort(key=deal_key)
        external_result_ids = tuple(str(getattr(deal, "ticket")) for deal in exit_deals)
        financial = 0.0
        for deal in exit_deals:
            financial += self._money(deal, "profit")
            financial += self._money(deal, "swap")
            financial += self._money(deal, "commission")
            financial += self._money(deal, "fee")

        outcome: Literal["WIN", "LOSS", "DRAW"]
        if financial > 0:
            outcome = "WIN"
        elif financial < 0:
            outcome = "LOSS"
        else:
            outcome = "DRAW"

        external_close_id = lineage.external_close_id or str(getattr(exit_deals[-1], "ticket", ""))
        if not external_close_id:
            return None
        if lineage.external_close_id is None:
            lineage = self.lineage.attach_external_close_id(
                lineage.request_id,
                external_close_id,
                updated_at=observed_at,
            )

        evidence = MT5OutcomeEvidence(
            decision_id=lineage.decision_id,
            cycle_id=lineage.cycle_id,
            request_id=lineage.request_id,
            external_container_id=lineage.external_container_id,
            external_close_id=external_close_id,
            external_result_ids=external_result_ids,
            financial_result=float(financial),
            outcome=outcome,
            observed_at=observed_at,
        )
        self.lineage.attach_external_result_ids(
            lineage.request_id,
            external_result_ids,
            updated_at=observed_at,
        )
        return evidence

    @classmethod
    def _entry_constants(cls, mt5: Any) -> set[Any]:
        values = {
            getattr(mt5, name, None)
            for name in cls._EXIT_ENTRIES
        }
        return {value for value in values if value is not None}

    @staticmethod
    def _money(deal: Any, name: str) -> float:
        value = getattr(deal, name, 0.0)
        if value is None:
            return 0.0
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MT5OutcomeBridgeError(f"deal {name} inválido.")
        return float(value)

    @staticmethod
    def _resolve_external_container_id(mt5: Any, external_id: str | None) -> str | None:
        if not external_id:
            return None
        try:
            ticket = int(external_id)
        except (TypeError, ValueError):
            return None

        deals = mt5.history_deals_get(ticket=ticket)
        if deals:
            for deal in deals:
                external_container_id = getattr(deal, "external_container_id", None)
                if external_container_id:
                    return str(external_container_id)

        orders = mt5.history_orders_get(ticket=ticket)
        if orders:
            for order in orders:
                external_container_id = getattr(order, "external_container_id", None)
                if external_container_id:
                    return str(external_container_id)

        return None

    @staticmethod
    def _get_single_position(mt5: Any, external_container_id: str) -> Any | None:
        positions = mt5.positions_get(ticket=int(external_container_id))
        if positions is None:
            return None
        items = list(positions)
        if len(items) > 1:
            raise MT5OutcomeBridgeError("mais de uma posição encontrada para o mesmo external_container_id.")
        return items[0] if items else None

    @staticmethod
    def _require_demo(mt5: Any) -> None:
        account = mt5.account_info()
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        if account is None or demo_mode is None or getattr(account, "trade_mode", None) != demo_mode:
            raise MT5OutcomeBridgeError("conta MT5 não confirmada como DEMO; operação bloqueada.")

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"
