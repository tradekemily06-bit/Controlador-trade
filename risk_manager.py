class RiskManager:
    """Camada de risco independente da corretora."""

    def __init__(self, daily_limit=0.0):
        self.daily_limit = daily_limit

    def can_execute(self, *, daily_result: float) -> bool:
        if self.daily_limit <= 0:
            return True
        return daily_result > -abs(self.daily_limit)
