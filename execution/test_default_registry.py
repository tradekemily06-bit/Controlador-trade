from core.kill_switch import KillSwitch
from core.models import Signal
from execution.default_registry import (
    IC_MARKETS_MT5_DEMO,
    build_demo_registry,
    build_ic_markets_mt5_demo_gateway,
)
from execution.gateway import GatewayStatus
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.ports import ExecutionMode, ExecutionRequest


def test_default_demo_registry_registers_ic_markets_without_connecting():
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("registry construction must not initialize MT5")

    registry = build_demo_registry(mt5_module=UnusedMT5())

    assert registry.names() == (IC_MARKETS_MT5_DEMO,)
    assert isinstance(registry.get(IC_MARKETS_MT5_DEMO), ICMarketsMT5DemoAdapter)


def test_default_demo_registry_can_override_symbol():
    registry = build_demo_registry(symbol="EURUSD")
    adapter = registry.get(IC_MARKETS_MT5_DEMO)

    assert adapter.config.symbol == "EURUSD"


def test_ic_markets_demo_gateway_is_composed_without_connecting():
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("gateway construction must not initialize MT5")

    gateway = build_ic_markets_mt5_demo_gateway(mt5_module=UnusedMT5(), symbol="EURUSD")

    assert gateway is not None


def test_ic_markets_demo_gateway_keeps_real_blocked_before_adapter_access():
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("REAL must be blocked before MT5 access")

    gateway = build_ic_markets_mt5_demo_gateway(mt5_module=UnusedMT5())
    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.REAL,
        request_id="real-blocked",
    )

    result = gateway.execute("real-blocked", request)

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_ic_markets_demo_gateway_kill_switch_blocks_before_adapter():
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("kill switch must block before MT5 access")

    kill_switch = KillSwitch()
    kill_switch.activate("teste de segurança")
    gateway = build_ic_markets_mt5_demo_gateway(
        mt5_module=UnusedMT5(),
        kill_switch=kill_switch,
    )
    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id="demo-kill-switch",
    )

    result = gateway.execute("demo-kill-switch", request)

    assert result.status is GatewayStatus.BLOCKED
