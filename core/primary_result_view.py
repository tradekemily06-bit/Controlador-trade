"""UI-facing view model for making the primary trading result obvious."""
from dataclasses import dataclass

from .api_presentation import PresentationToken, presentation_for_signal, real_blocked_token
from .models import AnalysisResult


@dataclass(frozen=True)
class PrimaryResultView:
    result: AnalysisResult
    primary: PresentationToken
    real_security: PresentationToken


def build_primary_result_view(result: AnalysisResult) -> PrimaryResultView:
    """Build a deterministic view model without changing the trading decision."""
    if not isinstance(result, AnalysisResult):
        raise TypeError("result must be an AnalysisResult")
    return PrimaryResultView(
        result=result,
        primary=presentation_for_signal(result.signal),
        real_security=real_blocked_token(),
    )
