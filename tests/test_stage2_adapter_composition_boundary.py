from pathlib import Path

from core.models import Signal
from execution.default_registry import build_ic_markets_mt5_demo_gateway
from execution.demo_broker_port import DemoBrokerExecutionPort, GatewayBoundDemoExecutionPort, build_ic_markets_mt5_demo_port
from execution.ports import ExecutionMode, ExecutionRequest


def _request(mode: ExecutionMode = ExecutionMode.DEMO) -> ExecutionRequest:
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=mode,
        request_id="stage2-boundary",
    )


def test_operational_mt5_factory_never_injects_raw_adapter(tmp_path: Path):
    gateway = build_ic_markets_mt5_demo_gateway(runtime_root=tmp_path)

    assert isinstance(gateway._executor, GatewayBoundDemoExecutionPort)
    assert not isinstance(gateway._executor, DemoBrokerExecutionPort)


def test_public_mt5_demo_port_direct_execute_is_non_dispatching():
    port = build_ic_markets_mt5_demo_port()

    result = port.execute(_request())

    assert result.accepted is False
    assert "dispatch direto" in result.message


def test_public_mt5_demo_port_rejects_real_mode_before_broker_dispatch():
    port = build_ic_markets_mt5_demo_port()

    result = port.execute(_request(ExecutionMode.REAL))

    assert result.accepted is False
    assert "fora do modo DEMO" in result.message
