from dataclasses import dataclass
import math

from .operational_state import OperationalState


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


_UNSET = object()


class RiskManager:
    """Gerencia limites de risco independentemente da corretora."""

    def __init__(
        self,
        *,
        daily_loss_limit=0.0,
        max_operations=0,
        max_consecutive_losses=0,
    ):
        self.daily_loss_limit = self._non_negative_number(
            daily_loss_limit,
            "daily_loss_limit",
        )
        self.max_operations = self._non_negative_integer(
            max_operations,
            "max_operations",
        )
        self.max_consecutive_losses = self._non_negative_integer(
            max_consecutive_losses,
            "max_consecutive_losses",
        )

    @staticmethod
    def _non_negative_number(value, name):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError(
                f"{name} deve ser um número finito não negativo."
            )
        return float(value)

    @staticmethod
    def _non_negative_integer(value, name):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError(
                f"{name} deve ser um inteiro não negativo."
            )
        return value

    def evaluate(
        self,
        *,
        state=None,
        daily_result=_UNSET,
        operations_count=_UNSET,
        consecutive_losses=_UNSET,
    ):
        """
        Evaluate risk from an explicit OperationalState.

        Legacy arguments are accepted only when all three are explicitly
        supplied. Missing information is never converted into approval.
        """

        if state is None:
            legacy_supplied = (
                daily_result is not _UNSET
                and operations_count is not _UNSET
                and consecutive_losses is not _UNSET
            )

            if not legacy_supplied:
                return RiskDecision(
                    False,
                    "Estado operacional indisponível.",
                )

            try:
                state = OperationalState(
                    realized_pnl=daily_result,
                    trades_today=operations_count,
                    consecutive_losses=consecutive_losses,
                )
            except (TypeError, ValueError):
                return RiskDecision(
                    False,
                    "Estado operacional inválido.",
                )

        if not isinstance(state, OperationalState):
            return RiskDecision(
                False,
                "Estado operacional inválido.",
            )

        if not state.risk_fields_available():
            return RiskDecision(
                False,
                "Informações obrigatórias de risco indisponíveis.",
            )

        if (
            self.daily_loss_limit != 0
            and state.realized_pnl is None
        ):
            return RiskDecision(
                False,
                "Resultado diário indisponível.",
            )

        if (
            self.max_operations != 0
            and state.trades_today >= self.max_operations
        ):
            return RiskDecision(
                False,
                "Limite de operações atingido.",
            )

        if (
            self.max_consecutive_losses != 0
            and state.consecutive_losses >= self.max_consecutive_losses
        ):
            return RiskDecision(
                False,
                "Limite de perdas consecutivas atingido.",
            )

        if (
            self.daily_loss_limit != 0
            and state.realized_pnl <= -abs(self.daily_loss_limit)
        ):
            return RiskDecision(
                False,
                "Limite de perda diária atingido.",
            )

        return RiskDecision(
            True,
            "Risco dentro dos limites configurados.",
        )

    def can_execute(
        self,
        *,
        state=None,
        daily_result=_UNSET,
        operations_count=_UNSET,
        consecutive_losses=_UNSET,
    ):
        return self.evaluate(
            state=state,
            daily_result=daily_result,
            operations_count=operations_count,
            consecutive_losses=consecutive_losses,
        ).allowed

    @staticmethod
    def calculate_position_risk(*, account_balance, risk_percent):
        if (
            isinstance(account_balance, bool)
            or not isinstance(account_balance, (int, float))
            or not math.isfinite(float(account_balance))
            or account_balance < 0
        ):
            raise ValueError("Saldo deve ser um número finito não negativo.")

        if (
            isinstance(risk_percent, bool)
            or not isinstance(risk_percent, (int, float))
            or not math.isfinite(float(risk_percent))
            or not 0 <= risk_percent <= 100
        ):
            raise ValueError(
                "risk_percent deve ser um número entre 0 e 100."
            )

        return account_balance * (risk_percent / 100.0)
