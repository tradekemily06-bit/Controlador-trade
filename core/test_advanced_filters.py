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


def test_allows_aligned_buy_setup():
    result = AdvancedFilters().evaluate(**make_values(), direction="BUY")
    assert result.allowed is True
    assert result.reasons == ()


def test_allows_aligned_sell_setup():
    result = AdvancedFilters().evaluate(
        trend=20.0, pressure=20.0, structure=20.0, rejection=40.0, volume=30.0,
        confirmation=100.0, direction="SELL",
    )
    assert result.allowed is True
    assert result.reasons == ()


def test_blocks_without_confirmation():
    result = AdvancedFilters().evaluate(**make_values(confirmation=0.0), direction="BUY")
    assert result.allowed is False
    assert "Confirmação insuficiente." in result.reasons


def test_directional_filter_does_not_block_valid_sell():
    result = AdvancedFilters().evaluate(
        trend=20.0, pressure=20.0, structure=20.0, rejection=40.0, volume=30.0,
        confirmation=100.0, direction="SELL",
    )
    assert result.allowed is True


def test_blocks_sell_when_one_component_conflicts():
    result = AdvancedFilters().evaluate(
        trend=20.0, pressure=20.0, structure=80.0, rejection=40.0, volume=30.0,
        confirmation=100.0, direction="SELL",
    )
    assert result.allowed is False
    assert any("Structure" in reason for reason in result.reasons)


def test_rejects_invalid_values_fail_closed():
    for value in (math.nan, math.inf, -1.0, 101.0, True, "100"):
        result = AdvancedFilters().evaluate(**make_values(volume=value), direction="BUY")
        assert result.allowed is False
        assert result.reasons == ("volume inválido.",)


def test_requires_direction_for_actionable_alignment():
    result = AdvancedFilters().evaluate(**make_values())
    assert result.allowed is False
    assert "Sem direção candidata suficientemente definida." in result.reasons
