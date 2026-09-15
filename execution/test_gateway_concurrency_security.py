from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def _request(*, risk_state_fingerprint: str | None = None, market_data_fingerprint: str | None = None) -> ExecutionRequest:
    return ExecutionRequest(symbol="TEST", signal=Signal.COMPRA, amount=10.0, duration_seconds=60, mode=ExecutionMode.DEMO, risk_state_fingerprint=risk_state_fingerprint, market_data_fingerprint=market_data_fingerprint)


def test_concurrent_gateways_only_one_worker_can_reserve_same_request_id(tmp_path: Path):
    path = tmp_path / "ledger.json"
    gateways = [ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path)) for _ in range(16)]
    def attempt(index: int):
        return gateways[index].execute("same-concurrent-id", _request())
    with ThreadPoolExecutor(max_workers=len(gateways)) as pool:
        results = list(pool.map(attempt, range(len(gateways))))
    accepted = [result for result in results if result.status is GatewayStatus.ACCEPTED]
    duplicates = [result for result in results if result.status is GatewayStatus.DUPLICATE]
    assert len(accepted) == 1
    assert len(duplicates) == 15
    assert ExecutionLedger(path).records() == ("same-concurrent-id",)


def test_risk_state_change_after_reservation_blocks_dispatch_and_marks_unknown(tmp_path: Path):
    path = tmp_path / "ledger.json"
    executor = PaperExecutor()
    expected, changed, calls = "a" * 64, "b" * 64, 0
    def risk_provider() -> str:
        nonlocal calls
        calls += 1
        return expected if calls == 1 else changed
    gateway = ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path), risk_state_fingerprint_provider=risk_provider)
    result = gateway.execute("risk-race", _request(risk_state_fingerprint=expected))
    assert result.status is GatewayStatus.BLOCKED
    assert "estado de risco mudou" in result.message
    assert calls >= 2
    assert executor.executions() == ()
    assert ExecutionLedger(path).status("risk-race") is ExecutionLedgerStatus.UNKNOWN


def test_market_data_change_after_reservation_blocks_dispatch_and_marks_unknown(tmp_path: Path):
    path = tmp_path / "ledger.json"
    executor = PaperExecutor()
    expected, changed, calls = "c" * 64, "d" * 64, 0
    def market_provider() -> str:
        nonlocal calls
        calls += 1
        return expected if calls == 1 else changed
    gateway = ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path), market_data_fingerprint_provider=market_provider)
    result = gateway.execute("market-race", _request(market_data_fingerprint=expected))
    assert result.status is GatewayStatus.BLOCKED
    assert "dados de mercado mudaram" in result.message
    assert calls >= 2
    assert executor.executions() == ()
    assert ExecutionLedger(path).status("market-race") is ExecutionLedgerStatus.UNKNOWN


def test_global_barrier_change_after_reservation_blocks_dispatch_and_marks_unknown(tmp_path: Path):
    path = tmp_path / "ledger.json"
    executor = PaperExecutor()
    calls = 0
    def barrier_provider() -> GlobalOperationalBarrier:
        nonlocal calls
        calls += 1
        if calls == 1:
            return GlobalOperationalBarrier()
        return GlobalOperationalBarrier((SafetyComponent(name="technical-incident", healthy=False, detail="incidente aberto depois da reserva"),))
    gateway = ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path), operational_barrier_provider=barrier_provider)
    result = gateway.execute("barrier-race", _request())
    assert result.status is GatewayStatus.BLOCKED
    assert "barreira operacional global" in result.message
    assert calls >= 2
    assert executor.executions() == ()
    assert ExecutionLedger(path).status("barrier-race") is ExecutionLedgerStatus.UNKNOWN


def test_unknown_request_remains_blocked_after_restart_until_reconciliation(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("restart-unknown")
    ledger.mark_unknown("restart-unknown")
    restarted_executor = PaperExecutor()
    restarted = ExecutionGateway(restarted_executor, KillSwitch(), ledger=ExecutionLedger(path))
    result = restarted.execute("restart-unknown", _request())
    assert result.status is GatewayStatus.BLOCKED
    assert "estado incerto" in result.message
    assert restarted_executor.executions() == ()
    assert ExecutionLedger(path).status("restart-unknown") is ExecutionLedgerStatus.UNKNOWN
