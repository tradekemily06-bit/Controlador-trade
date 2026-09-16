from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from core.global_operational_barrier import GlobalOperationalBarrier
from core.test_p111_p119_real_release import (
    _admission,
    _authorization,
    _request,
    _risk_state,
    _safety,
    _snapshot,
    FakeRealSafetyProvider,
    FakeRiskStateProvider,
)
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class AmbiguousAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def execute(self, request) -> ExecutionResult:
        self.calls += 1
        raise RuntimeError("broker response lost after submission")


def _gateway(ledger_path: Path, adapter: AmbiguousAdapter) -> RealExecutionGateway:
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    auth = _authorization()
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        FakeRiskStateProvider(_risk_state()),
        FakeRealSafetyProvider(_safety(auth)),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )


def test_restart_after_unknown_never_replays_the_order(tmp_path: Path) -> None:
    ledger_path = tmp_path / "restart-ledger.json"
    request_id = "restart-unknown"
    auth = _authorization()
    safety = _safety(auth)
    request = replace(_request(), request_id=request_id)

    first_adapter = AmbiguousAdapter()
    first_gateway = _gateway(ledger_path, first_adapter)
    first = first_gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request,
        authorization=auth,
        admission=_admission(auth),
        safety=safety,
        snapshot=_snapshot(),
    )

    assert first.status is RealGatewayStatus.UNKNOWN
    assert first_adapter.calls == 1
    assert ExecutionLedger(ledger_path).status(request_id) is ExecutionLedgerStatus.UNKNOWN

    # Simulated process restart: new gateway, new adapter object, same durable ledger.
    second_adapter = AmbiguousAdapter()
    second_gateway = _gateway(ledger_path, second_adapter)
    second = second_gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request,
        authorization=auth,
        admission=_admission(auth),
        safety=safety,
        snapshot=_snapshot(),
    )

    assert second.status is RealGatewayStatus.UNKNOWN
    assert second_adapter.calls == 0
    assert ExecutionLedger(ledger_path).status(request_id) is ExecutionLedgerStatus.UNKNOWN

    second_gateway.reconcile_unknown(request_id, executed=False)
    assert ExecutionLedger(ledger_path).status(request_id) is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED

    # Reconciliation is not a new authorization: the same request ID remains terminal.
    third = second_gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request,
        authorization=auth,
        admission=_admission(auth),
        safety=safety,
        snapshot=_snapshot(),
    )
    assert third.status is RealGatewayStatus.BLOCKED
    assert second_adapter.calls == 0
