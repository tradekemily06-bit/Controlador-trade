from __future__ import annotations

from typing import Any

from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderQueryPort, ExternalOrderStatus


class MT5ExternalOrderQueryError(RuntimeError):
    """Raised when MT5 cannot safely answer an external-order query."""


class ICMarketsMT5DemoOrderQueryAdapter(ExternalOrderQueryPort):
    """Read-only MT5 DEMO query adapter; it never sends or modifies orders."""

    def __init__(self, mt5_module: Any = None) -> None:
        self._mt5 = mt5_module

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5ExternalOrderQueryError("MetaTrader5 não instalado.") from exc
            self._mt5 = mt5
        return self._mt5

    def query_order(self, external_id: str) -> ExternalOrderObservation:
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")
        try:
            ticket = int(external_id.strip())
        except ValueError as exc:
            raise ValueError("external_id MT5 deve ser um ticket numérico.") from exc
        if ticket <= 0:
            raise ValueError("external_id MT5 inválido.")

        mt5 = self._module()
        if not mt5.initialize():
            raise MT5ExternalOrderQueryError(f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            account = mt5.account_info()
            demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
            if account is None or demo_mode is None or getattr(account, "trade_mode", None) != demo_mode:
                return ExternalOrderObservation(external_id.strip(), ExternalOrderStatus.UNKNOWN, "conta MT5 não confirmada como DEMO.")

            active = self._first(mt5.orders_get(ticket=ticket))
            if active is not None:
                return self._map_active(mt5, external_id.strip(), active)

            history = self._first(mt5.history_orders_get(ticket=ticket))
            if history is not None:
                return self._map_history(mt5, external_id.strip(), history)

            deals = self._first(mt5.history_deals_get(ticket=ticket))
            if deals is not None:
                return ExternalOrderObservation(external_id.strip(), ExternalOrderStatus.EXECUTED, "deal MT5 encontrado no histórico.")

            return ExternalOrderObservation(external_id.strip(), ExternalOrderStatus.UNKNOWN, "ticket MT5 não encontrado nas ordens/deals consultados.")
        except Exception as exc:
            return ExternalOrderObservation(external_id.strip(), ExternalOrderStatus.UNKNOWN, f"falha na consulta MT5: {type(exc).__name__}: {exc}")
        finally:
            try:
                mt5.shutdown()
            except Exception:
                pass

    @staticmethod
    def _first(items: Any) -> Any:
        if items is None:
            return None
        try:
            return next(iter(items), None)
        except TypeError:
            return None

    @staticmethod
    def _map_active(mt5: Any, external_id: str, order: Any) -> ExternalOrderObservation:
        state = getattr(order, "state", None)
        pending_states = {getattr(mt5, name, object()) for name in ("ORDER_STATE_PLACED", "ORDER_STATE_STARTED", "ORDER_STATE_PARTIAL")}
        if state in pending_states:
            return ExternalOrderObservation(external_id, ExternalOrderStatus.PENDING, f"ordem MT5 ativa: state={state}")
        return ExternalOrderObservation(external_id, ExternalOrderStatus.UNKNOWN, f"ordem MT5 ativa em estado não mapeado: state={state}")

    @staticmethod
    def _map_history(mt5: Any, external_id: str, order: Any) -> ExternalOrderObservation:
        state = getattr(order, "state", None)
        done = getattr(mt5, "ORDER_STATE_FILLED", None)
        not_executed_states = {
            getattr(mt5, "ORDER_STATE_CANCELED", object()),
            getattr(mt5, "ORDER_STATE_REJECTED", object()),
            getattr(mt5, "ORDER_STATE_EXPIRED", object()),
            getattr(mt5, "ORDER_STATE_REQUEST_ADD", object()),
            getattr(mt5, "ORDER_STATE_REQUEST_CANCEL", object()),
        }
        if done is not None and state == done:
            return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, f"ordem MT5 preenchida: state={state}")
        if state in not_executed_states:
            return ExternalOrderObservation(external_id, ExternalOrderStatus.NOT_EXECUTED, f"ordem MT5 não executada: state={state}")
        return ExternalOrderObservation(external_id, ExternalOrderStatus.UNKNOWN, f"estado histórico MT5 não mapeado: state={state}")

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"
