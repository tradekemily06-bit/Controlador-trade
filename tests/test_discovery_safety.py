from core.discovery_safety import assess_discovery_safety, is_operationally_admitted


def test_discovery_is_observation_only():
    result = assess_discovery_safety(("RANGE_DIRECTION=UP", "VOLUME_DIRECTION=UP"))
    assert result.status == "OBSERVATION_ONLY"
    assert result.execution_authorized is False
    assert result.relationships == ("RANGE_DIRECTION=UP", "VOLUME_DIRECTION=UP")


def test_empty_discovery_is_safe_and_non_authorizing():
    result = assess_discovery_safety(())
    assert result.status == "NO_DISCOVERY"
    assert result.execution_authorized is False


def test_discovery_cannot_become_operational_without_ecosystem_tests():
    assert is_operationally_admitted(
        tests_passed=False,
        explicitly_admitted=True,
    ) is False


def test_discovery_cannot_become_operational_without_explicit_admission():
    assert is_operationally_admitted(
        tests_passed=True,
        explicitly_admitted=False,
    ) is False


def test_discovery_becomes_eligible_only_after_both_gates():
    assert is_operationally_admitted(
        tests_passed=True,
        explicitly_admitted=True,
    ) is True
