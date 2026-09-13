import pytest

from core.senior_market_professional_standard import (
    SENIOR_FINANCIAL_MARKET_STANDARD,
    SeniorCapabilityStandard,
    SeniorDimension,
    assert_senior_standard,
)


def test_canonical_standard_covers_all_senior_dimensions_and_no_execution_authority():
    standard = assert_senior_standard()
    assert standard is SENIOR_FINANCIAL_MARKET_STANDARD
    assert set(standard.dimensions) == set(SeniorDimension)
    assert standard.execution_authorized is False
    assert standard.handles_conflicts is True
    assert standard.handles_exceptions is True
    assert standard.requires_provenance is True
    assert standard.requires_reassessment is True


def test_incomplete_capability_is_rejected():
    standard = SeniorCapabilityStandard(
        capability_id="partial",
        domains=("markets",),
        dimensions=(SeniorDimension.KNOWLEDGE,),
    )
    with pytest.raises(ValueError, match="incomplete"):
        standard.validate()


def test_quality_contract_cannot_be_used_to_grant_execution_authority():
    standard = SeniorCapabilityStandard(
        capability_id="unsafe",
        domains=("markets",),
        dimensions=tuple(SeniorDimension),
        execution_authorized=True,
    )
    with pytest.raises(ValueError, match="execution authority"):
        standard.validate()
