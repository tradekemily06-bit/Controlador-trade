from core.discovery_safety import assess_discovery_safety


def test_discovery_is_observation_only():
    result = assess_discovery_safety(("RANGE_DIRECTION=UP", "VOLUME_DIRECTION=UP"))
    assert result.status == "OBSERVATION_ONLY"
    assert result.execution_authorized is False
    assert result.relationships == ("RANGE_DIRECTION=UP", "VOLUME_DIRECTION=UP")


def test_empty_discovery_is_safe_and_non_authorizing():
    result = assess_discovery_safety(())
    assert result.status == "NO_DISCOVERY"
    assert result.execution_authorized is False
