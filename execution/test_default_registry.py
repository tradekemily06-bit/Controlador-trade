from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.default_registry import IC_MARKETS_MT5_DEMO, build_ic_markets_mt5_demo_gateway
from execution.broker_registry import BrokerRegistry
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig


def _build_demo_registry(*, mt5_module=None, symbol=None):
    registry = BrokerRegistry()
    registry.register(IC_MARKETS_MT5_DEMO, ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol=symbol), mt5_module=mt5_module))
    return registry
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.gateway import GatewayStatus
from execution.mt5_demo_risk_state_provider import MT5DemoRiskStateProvider
from execution.ports import ExecutionMode, ExecutionRequest


def test_default_demo_registry_registers_ic_markets_without_connecting():
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("registry construction must not initialize MT5")

    registry = _build_demo_registry(mt5_module=UnusedMT5())

    assert registry.names() == (IC_MARKETS_MT5_DEMO,)
    assert registry.info()[0].name == IC_MARKETS_MT5_DEMO
    assert registry.info()[0].available is False


def test_default_demo_registry_can_override_symbol_without_exposing_adapter_lookup():
    registry = _build_demo_registry(symbol="EURUSD")
    metadata = registry.as_mapping()[IC_MARKETS_MT5_DEMO]

    assert metadata.name == IC_MARKETS_MT5_DEMO
    assert metadata.available is False
    try:
        registry._get_for_gateway(IC_MARKETS_MT5_DEMO, capability=object())
    except ValueError as exc:
        assert "barreira" in str(exc)
    else:
        raise AssertionError("adapter lookup must require the gateway capability")


def test_ic_markets_demo_gateway_is_composed_without_connecting(tmp_path: Path):
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("gateway construction must not initialize MT5")

    gateway = build_ic_markets_mt5_demo_gateway(
        mt5_module=UnusedMT5(),
        symbol="EURUSD",
        runtime_root=tmp_path,
    )

    assert gateway is not None
    assert isinstance(gateway._risk_state_provider, MT5DemoRiskStateProvider)
    assert isinstance(gateway._ledger, ExecutionLedger)
    assert isinstance(gateway._lifecycle, ExecutionLifecycleStore)
    assert gateway._safety_store is not None
    assert gateway._maintenance is not None
    assert gateway._dispatch_lock_path is not None


def test_ic_markets_demo_factory_never_returns_a_bare_gateway(tmp_path: Path):
    gateway = build_ic_markets_mt5_demo_gateway(runtime_root=tmp_path)

    required = (
        gateway._ledger,
        gateway._lifecycle,
        gateway._maintenance,
        gateway._safety_store,
        gateway._dispatch_lock_path,
        gateway._risk_state_provider,
    )
    assert all(item is not None for item in required)
    assert gateway._dispatch_lock_path.parent == tmp_path


def test_ic_markets_demo_gateway_risk_provider_uses_same_broker_edge_module(tmp_path: Path):
    class UnusedMT5:
        pass

    mt5 = UnusedMT5()
    gateway = build_ic_markets_mt5_demo_gateway(
        mt5_module=mt5, symbol="EURUSD", timeframe=5, runtime_root=tmp_path
    )

    assert gateway._risk_state_provider._mt5 is mt5
    assert gateway._risk_state_provider.config.symbol == "EURUSD"
    assert gateway._risk_state_provider.config.timeframe == 5


def test_ic_markets_demo_gateway_rejects_invalid_timeframe():
    try:
        build_ic_markets_mt5_demo_gateway(timeframe=0)
    except ValueError as exc:
        assert "timeframe" in str(exc)
    else:
        raise AssertionError("invalid timeframe must be rejected")


def test_ic_markets_demo_gateway_keeps_real_blocked_before_adapter_access(tmp_path: Path):
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("REAL must be blocked before MT5 access")

    gateway = build_ic_markets_mt5_demo_gateway(mt5_module=UnusedMT5(), runtime_root=tmp_path)
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


def test_ic_markets_demo_gateway_kill_switch_blocks_before_adapter(tmp_path: Path):
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("kill switch must block before MT5 access")

    kill_switch = KillSwitch()
    kill_switch.activate("teste de segurança")
    gateway = build_ic_markets_mt5_demo_gateway(
        mt5_module=UnusedMT5(),
        kill_switch=kill_switch,
        runtime_root=tmp_path,
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
