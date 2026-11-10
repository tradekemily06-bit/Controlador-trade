from __future__ import annotations

from pathlib import Path

from core.operational_runtime import build_operational_runtime
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from integration.execution_provider import build_demo_execution_port


def test_selected_mt5_demo_provider_can_be_injected_without_core_importing_mt5(tmp_path: Path):
    executor = build_demo_execution_port("ic_markets_mt5_demo", symbol="EURUSD")
    runtime = build_operational_runtime(tmp_path, executor=executor)
    assert isinstance(runtime.gateway._executor, ICMarketsMT5DemoAdapter)


def test_mt5_demo_provider_uses_explicit_risk_day_timezone(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_RISK_DAY_TIMEZONE", "America/Sao_Paulo")
    executor = build_demo_execution_port("ic_markets_mt5_demo", symbol="EURUSD")
    assert executor.config.risk_day_timezone == "America/Sao_Paulo"

    

def test_mt5_demo_provider_pins_configured_terminal_path(monkeypatch):
    terminal_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    monkeypatch.setenv("CONTROLADOR_MT5_TERMINAL_PATH", terminal_path)
    executor = build_demo_execution_port("ic_markets_mt5_demo", symbol="EURUSD")
    assert executor.config.terminal_path == terminal_path
