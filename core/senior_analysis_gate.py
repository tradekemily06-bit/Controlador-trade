"""Gate contextual entre análise candidata e decisão operacional.

O score legado pode continuar existindo como evidência auxiliar, mas nunca
pode, sozinho, transformar uma análise em COMPRA/VENDA. A leitura integrada
precisa sustentar a direção e o ciclo sênior precisa estar completo. Este
módulo não concede autoridade de execução.
"""

from __future__ import annotations

from core.models import AnalysisResult, Signal
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.integrated_market_reading import ReadingStatus


class SeniorAnalysisGate:
    """Impede que score/um único subsistema opere isoladamente."""

    def evaluate(
        self,
        *,
        analysis: AnalysisResult,
        senior_context: SeniorContextCycle,
    ) -> AnalysisResult:
        if not isinstance(analysis, AnalysisResult):
            raise ValueError("analysis must be AnalysisResult")
        if not isinstance(senior_context, SeniorContextCycle):
            raise ValueError("senior_context must be SeniorContextCycle")

        if analysis.signal is Signal.AGUARDAR:
            return analysis

        if senior_context.execution_authorized:
            return self._await(analysis, "O contexto sênior não pode conceder autoridade de execução.")

        if senior_context.quality is not SeniorContextQuality.COMPLETE:
            return self._await(analysis, "A leitura sênior está incompleta e exige reavaliação.")

        reading = senior_context.market_reading
        if reading.status is not ReadingStatus.SUPPORTED:
            return self._await(analysis, "A leitura integrada não está suficientemente sustentada.")

        expected_direction = "BUY" if analysis.signal is Signal.COMPRA else "SELL"
        supported = {
            observation.observation_id
            for observation in reading.observations
            if observation.direction == expected_direction and observation.strength > 0
        }
        if not supported:
            return self._await(analysis, "A direção candidata não é sustentada pela leitura integrada.")

        return AnalysisResult(
            signal=analysis.signal,
            score=analysis.score,
            reason=(
                "Análise candidata confirmada pela leitura integrada e pelo ciclo sênior; "
                "execução continua sujeita aos gates operacionais, de risco e segurança."
            ),
            confirmed=analysis.confirmed,
            symbol=analysis.symbol,
            timeframe=analysis.timeframe,
        )

    @staticmethod
    def _await(analysis: AnalysisResult, reason: str) -> AnalysisResult:
        return AnalysisResult(
            signal=Signal.AGUARDAR,
            score=analysis.score,
            reason=reason,
            confirmed=False,
            symbol=analysis.symbol,
            timeframe=analysis.timeframe,
        )
