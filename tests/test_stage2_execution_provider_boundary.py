import pytest

from integration.execution_provider import ExecutionProviderConfigurationError, build_demo_execution_port


@pytest.mark.parametrize(
    "provider",
    ["real", "REAL", "live", "LIVE", "real_execution", "broker_real", "mt5_real", "ic_markets_mt5_real"],
)
def test_known_real_provider_aliases_fail_closed(provider):
    with pytest.raises(ExecutionProviderConfigurationError):
        build_demo_execution_port(provider)


def test_unknown_provider_does_not_fall_back_to_paper():
    with pytest.raises(ExecutionProviderConfigurationError):
        build_demo_execution_port("anything-unrecognized")


def test_paper_remains_explicit_demo_provider():
    executor = build_demo_execution_port("paper")
    assert executor is not None
