from __future__ import annotations

from dataclasses import dataclass

from core.models import AnalysisResult
from core.signal_quality import SignalQuality, evaluate_signal_quality


@dataclass(frozen=True)
class DecisionSnapshot:
    """Registro explicável do sinal produzido pela análise."""

    analysis: AnalysisResult
    quality: SignalQuality

    @property
    def signal(self):
        return self.analysis.signal

    @property
    def score(self):
        return self.analysis.score

    @property
    def confirmed(self):
        return self.analysis.confirmed

    @property
    def reason(self):
        return self.analysis.reason


class DecisionSnapshotBuilder:
    """Converte o resultado técnico em um snapshot imutável e auditável."""

    def build(self, analysis: AnalysisResult) -> DecisionSnapshot:
        return DecisionSnapshot(
            analysis=analysis,
            quality=evaluate_signal_quality(analysis),
        )
