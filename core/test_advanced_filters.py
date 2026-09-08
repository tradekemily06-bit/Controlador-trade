import math

from core.advanced_filters import AdvancedFilters


def make_values(**overrides):
    values = {
        "trend": 80.0,
        "pressure": 80.0,
        "structure": 80.0,
        "rejection": 60.0,
        "volume": 70.0,
        "confirmation": 100.0,
    }
    values.update(overrides)
    return values


def test_allows_aligned_confirmed_setup():
    result = AdvancedFilters().evaluate(**make_values())

    assert result.allowed is True
    assert result.reasons == ()


def test_blocks_without_confirmation():
    result = AdvancedFilters().evaluate(**make_values(confirmation=0.0))

    assert result.allowed is False
    assert "Confirmação insuficiente." in result.reasons


def test_blocks_when_core_component_is_below_minimum():
    result = AdvancedFilters().evaluate(**make_values(trend=49.0))

    assert result.allowed is False
    assert "Tendência insuficiente." in result.reasons


def test_rejection_can_be_weak_without_being_the_only_blocker():
    result = AdvancedFilters().evaluate(**make_values(rejection=10.0))

    assert result.allowed is False
    assert "Rejeição fraca." in result.reasons


def test_rejects_invalid_values_fail_closed():
    for value in (math.nan, math.inf, -1.0, 101.0, True, "100"):
        result = AdvancedFilters().evaluate(**make_values(volume=value))
        assert result.allowed is False
        assert result.reasons == ("volume inválido.",)


def test_reports_multiple_failed_conditions():
    result = AdvancedFilters().evaluate(
        **make_values(
            trend=20.0,
            pressure=30.0,
            structure=40.0,
            volume=10.0,
            confirmation=0.0,
        )
    )

    assert result.allowed is False
    assert len(result.reasons) == 5
