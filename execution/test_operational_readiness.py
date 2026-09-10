from execution.mt5_demo_health import MT5DemoHealth


def test_operational_readiness_documented_health_shape():
    healthy = MT5DemoHealth(True, True, "ok")
    blocked = MT5DemoHealth(False, False, "blocked")
    assert healthy.available is True
    assert healthy.demo_account is True
    assert blocked.available is False
    assert blocked.demo_account is False
