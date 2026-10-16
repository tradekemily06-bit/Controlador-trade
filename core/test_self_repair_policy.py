from core.self_repair_policy import RepairDecision, RepairRequest, SelfRepairPolicy


def safe_request(**overrides):
    values = {
        "action": "clear_stale_local_cache",
        "local_only": True,
        "reversible": True,
        "deterministic": True,
        "prevalidated": True,
        "external_side_effects": False,
        "touches_execution_state": False,
        "requires_human_supervision": False,
        "attempts_used": 0,
        "max_attempts": 1,
    }
    values.update(overrides)
    return RepairRequest(**values)


def test_allows_only_prevalidated_bounded_local_repair():
    result = SelfRepairPolicy.evaluate(safe_request())
    assert result.decision is RepairDecision.ALLOW_BOUNDED_REPAIR
    assert result.allowed is True


def test_blocks_non_reversible_or_external_repairs():
    for changes in (
        {"reversible": False},
        {"local_only": False},
        {"external_side_effects": True},
        {"deterministic": False},
        {"prevalidated": False},
        {"requires_human_supervision": True},
    ):
        result = SelfRepairPolicy.evaluate(safe_request(**changes))
        assert result.decision is RepairDecision.ALERT_AND_BLOCK
        assert result.allowed is False
        assert result.reason


def test_never_authorizes_repair_that_touches_execution_state():
    result = SelfRepairPolicy.evaluate(safe_request(touches_execution_state=True))
    assert result.decision is RepairDecision.ALERT_AND_BLOCK
    assert result.allowed is False


def test_blocks_after_attempt_limit():
    result = SelfRepairPolicy.evaluate(safe_request(attempts_used=1, max_attempts=1))
    assert result.decision is RepairDecision.ALERT_AND_BLOCK
    assert result.allowed is False


def test_invalid_request_fails_closed():
    result = SelfRepairPolicy.evaluate(object())
    assert result.decision is RepairDecision.ALERT_AND_BLOCK
    assert result.allowed is False
