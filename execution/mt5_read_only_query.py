from __future__ import annotations

from typing import Any

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderQueryPort,
    ExternalOrderStatus,
)


class MT5ReadOnlyOrderQuery(ExternalOrderQueryPort):
    """Read-only MT5 reconciliation boundary.

    This class deliberately has no order_send/order_check/close capability.
    It treats query failures and ambiguous broker state as UNKNOWN rather than
    inferring that an order was not executed.
    """

    def __init__(self, mt5_module: Any) -> None:
        if mt5_module is None:
            raise ValueError("mt5_module é obrigatório.")
        self._mt5 = mt5_module

    def query_order(self, external_id: str) -> ExternalOrderObservation:
        ticket = self._ticket(external_id)
        if ticket is None:
            return ExternalOrderObservation(
                external_id=None,
                status=ExternalOrderStatus.UNKNOWN,
                message="external_id não é um ticket MT5 válido; execução não pode ser inferida.",
            )

        try:
            active = self._mt5.orders_get(ticket=ticket)
        except Exception as exc:
            return self._unknown(ticket, f"consulta de ordem ativa falhou: {type(exc).__name__}")
        if active is None:
            return self._unknown(ticket, "MT5 não retornou a consulta de ordem ativa; execução é desconhecida.")
        if active:
            order = active[0]
            if self._looks_partially_filled(order):
                return ExternalOrderObservation(
                    str(ticket),
                    ExternalOrderStatus.UNKNOWN,
                    "ordem ainda ativa com indício de preenchimento parcial; estado não é terminal.",
                )
            return ExternalOrderObservation(
                str(ticket),
                ExternalOrderStatus.PENDING,
                "ordem ainda presente entre as ordens ativas do MT5.",
            )

        try:
            history = self._mt5.history_orders_get(ticket=ticket)
        except Exception as exc:
            return self._unknown(ticket, f"consulta do histórico de ordens falhou: {type(exc).__name__}")
        if history is None:
            return self._unknown(ticket, "MT5 não retornou o histórico da ordem; execução é desconhecida.")
        if history:
            order = history[-1]
            deals = self._history_deals(ticket)
            if deals is None:
                return self._unknown(ticket, "histórico de deals indisponível; não é seguro concluir o resultado.")
            if deals:
                return ExternalOrderObservation(
                    str(ticket),
                    ExternalOrderStatus.EXECUTED,
                    "deal encontrado no histórico do MT5.",
                )
            state = getattr(order, "state", None)
            if self._is_state(state, "ORDER_STATE_FILLED"):
                return ExternalOrderObservation(
                    str(ticket),
                    ExternalOrderStatus.EXECUTED,
                    "ordem histórica marcada como FILLED pelo MT5.",
                )
            if self._is_state(state, "ORDER_STATE_PARTIAL"):
                return ExternalOrderObservation(
                    str(ticket),
                    ExternalOrderStatus.UNKNOWN,
                    "ordem histórica indica preenchimento parcial; confirmação terminal insuficiente.",
                )
            if self._is_state(
                state,
                "ORDER_STATE_CANCELED",
                "ORDER_STATE_REJECTED",
                "ORDER_STATE_EXPIRED",
                "ORDER_STATE_REQUEST_CANCEL",
            ):
                return ExternalOrderObservation(
                    str(ticket),
                    ExternalOrderStatus.NOT_EXECUTED,
                    "ordem histórica em estado terminal sem deal associado.",
                )
            return self._unknown(ticket, "ordem histórica encontrada, mas seu estado não permite conclusão segura.")

        deals = self._history_deals(ticket)
        if deals is None:
            return self._unknown(ticket, "histórico de deals indisponível; ausência de ordem não prova não execução.")
        if deals:
            return ExternalOrderObservation(
                str(ticket),
                ExternalOrderStatus.EXECUTED,
                "deal encontrado no histórico do MT5.",
            )

        # An empty active/history/deal result is evidence only that these
        # queries returned no matching object; it is NOT proof of non-execution.
        return self._unknown(
            ticket,
            "nenhuma ordem/deal encontrado; ausência de evidência não prova não execução.",
        )

    def query_order_by_request_id(self, request_id: str) -> ExternalOrderObservation:
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id.strip()) > 128:
            raise ValueError("request_id inválido.")
        # MT5's MqlTradeResult.request_id is assigned by the terminal. It is
        # not the Controlador's request_id and is not a durable lookup key in
        # the Python history query API. Without an explicit persisted
        # correlation mapping, pretending these IDs are equal would be unsafe.
        return ExternalOrderObservation(
            external_id=None,
            status=ExternalOrderStatus.UNKNOWN,
            message="não há correlação MT5↔Controlador persistida para este request_id; reconciliação permanece UNKNOWN.",
            request_id=request_id.strip(),
        )

    def _history_deals(self, ticket: int) -> Any:
        try:
            return self._mt5.history_deals_get(ticket=ticket)
        except Exception:
            return None

    @staticmethod
    def _ticket(external_id: str) -> int | None:
        if not isinstance(external_id, str) or not external_id.strip():
            return None
        value = external_id.strip()
        try:
            ticket = int(value)
        except (TypeError, ValueError):
            return None
        return ticket if ticket > 0 else None

    @staticmethod
    def _looks_partially_filled(order: Any) -> bool:
        current = getattr(order, "volume_current", None)
        initial = getattr(order, "volume_initial", None)
        if not all(isinstance(v, (int, float)) for v in (current, initial)):
            return False
        return initial > 0 and 0 <= current < initial

    def _is_state(self, state: Any, *names: str) -> bool:
        return any(state == getattr(self._mt5, name, object()) for name in names)

    @staticmethod
    def _unknown(ticket: int, message: str) -> ExternalOrderObservation:
        return ExternalOrderObservation(str(ticket), ExternalOrderStatus.UNKNOWN, message)
