import pytest

from core.senior_context_cycle import SeniorContextCycle
from integration.p136_analysis_service_guard import AnalysisServiceGuard


def test_requires_context():
    with pytest.raises(ValueError, match="senior context is required"):
        AnalysisServiceGuard.require_senior_context({}, None)


def test_rejects_non_context():
    with pytest.raises(ValueError, match="senior context is invalid"):
        AnalysisServiceGuard.require_senior_context({}, object())


def test_rejects_execution_authority():
    # Any context claiming execution authority must never pass the analysis guard.
    context = object.__new__(SeniorContextCycle)
    context.execution_authorized = True
    with pytest.raises(ValueError, match="cannot authorize execution"):
        AnalysisServiceGuard.require_senior_context({}, context)
