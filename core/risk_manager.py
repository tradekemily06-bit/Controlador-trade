from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


class RiskManager:
    """Gerencia limites de risco independentemente da corretora."""

    def __init__(
        self,
        *,
        daily_loss_limit=0.0,
        max_operations=0,
        max_consecutive_losses=0,
    ):
        if daily_loss_limit < 0:
            raise ValueError("daily_loss_limit não pode ser negativo.")
        if max_operations < 0:
            raise ValueError("max_operations não pode ser negativo.")
        if max_consecutive_losses < 0:
            raise ValueError("max_consecutive_losses não pode ser negativo.")

        self.daily_loss_limit = float(daily_loss_limit)
        self.max_operations = int(max_operations)
        self.max_consecutive_losses = int(max_consecutive_losses)

    def evaluate(
        self,
        *,
        daily_result=0.0,
        operations_count=0,
        consecutive_losses=0,
    ):
        if self.daily_loss_limit != 0 and daily_result <= -abs(self.daily_loss_limit):
            return RiskDecision(False, "Limite de perda diária atingido.")

        if self.max_operations != 0 and operations_count >= self.max_operations:
            return RiskDecision(False, "Limite de operações atingido.")

        if (
            self.max_consecutive_losses != 0
            and consecutive_losses >= self.max_consecutive_losses
        ):
            return RiskDecision(
                False,
                "Limite de perdas consecutivas atingido.",
            )

        return RiskDecision(True, "Risco dentro dos limites configurados.")

    def can_execute(
        self,
        *,
        daily_result=0.0,
        operations_count=0,
        consecutive_losses=0,
    ):
        return self.evaluate(
            daily_result=daily_result,
            operations_count=operations_count,
            consecutive_losses=consecutive_losses,
        ).allowed

    @staticmethod
    def calculate_position_risk(*, account_balance, risk_percent):
        if account_balance < 0:
            raise ValueError("Saldo não pode ser negativo.")
        if not 0 <= risk_percent <= 100:
            raise ValueError("risk_percent deve estar entre 0 e 100.")

        return account_balance * (risk_percent / 100.0)
