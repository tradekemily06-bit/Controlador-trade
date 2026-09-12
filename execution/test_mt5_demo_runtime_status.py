from execution.mt5_demo_runtime_status import mt5_demo_runtime_status


def test_runtime_status_without_runtime_is_explicitly_unavailable():
    status = mt5_demo_runtime_status(object())

    assert status["state"] == "OFFLINE"
    assert status["available"] is False
    assert status["demo_account"] is False


def test_runtime_status_reports_demo_terminal_online():
    class DemoAccount:
        trade_mode = 7

    class FakeMT5:
        ACCOUNT_TRADE_MODE_DEMO = 7

        def initialize(self):
            return True

        def account_info(self):
            return DemoAccount()

        def shutdown(self):
            pass

    status = mt5_demo_runtime_status(FakeMT5())

    assert status == {
        "state": "ONLINE_DEMO",
        "available": True,
        "demo_account": True,
        "message": "MT5 DEMO disponível",
    }
