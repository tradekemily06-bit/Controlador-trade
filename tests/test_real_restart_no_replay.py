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
from threading import RLock

_REAL_FENCE = RLock()

def _test_real_barrier() -> GlobalOperationalBarrier:
    return GlobalOperationalBarrier(dispatch_fence_provider=lambda: _REAL_FENCE)
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


def _gateway(ledger_path: Path, adapter: AmbiguousAdapter, request_id: str = "restart-unknown", authority=None) -> RealExecutionGateway:
    registry = BrokerRegistry()
    registry.register("fake", adapter, adapter_id="fake-adapter")
    auth = _authorization(request_id=request_id)
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        FakeRiskStateProvider(_risk_state()),
        FakeRealSafetyProvider(_safety(auth)),
        operational_barrier_provider=lambda: _test_real_barrier(),
        reconciliation_evidence_verifier=authority,
    )


def test_restart_after_unknown_never_replays_the_order(tmp_path: Path) -> None:
    ledger_path = tmp_path / "restart-ledger.json"
    request_id = "restart-unknown"
    auth = _authorization(request_id=request_id)
    safety = _safety(auth)
    request = replace(_request(request_id=request_id), request_id=request_id)

    first_adapter = AmbiguousAdapter()
    first_gateway = _gateway(ledger_path, first_adapter, request_id)
    first = first_gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request,
        authorization=auth,
        admission=_admission(request_id=request_id, auth=auth, adapter_id="fake-adapter"),
        safety=safety,
        snapshot=_snapshot(),
    )

    assert first.status is RealGatewayStatus.UNKNOWN
    assert first_adapter.calls == 1
    assert ExecutionLedger(ledger_path).status(request_id) is ExecutionLedgerStatus.UNKNOWN

    # Simulated process restart: new gateway, new adapter object, same durable ledger.
    from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
    from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority
    query = type("Query", (), {"query_order": lambda self, external_id: ExternalOrderObservation(external_id, ExternalOrderStatus.NOT_EXECUTED, "authoritative", request_id=request_id, evidence_source="broker", broker_id="fake", symbol="TEST")})()
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    second_adapter = AmbiguousAdapter()
    second_gateway = _gateway(ledger_path, second_adapter, request_id, authority)
    second = second_gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request,
        authorization=auth,
        admission=_admission(request_id=request_id, auth=auth, adapter_id="fake-adapter"),
        safety=safety,
        snapshot=_snapshot(),
    )

    assert second.status is RealGatewayStatus.UNKNOWN
    assert second_adapter.calls == 0
    assert ExecutionLedger(ledger_path).status(request_id) is ExecutionLedgerStatus.UNKNOWN

    second_gateway.reconcile_unknown_with_evidence(request_id, executed=False, evidence_id="evidence-restart-unknown", evidence_source="broker")
    assert ExecutionLedger(ledger_path).status(request_id) is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED

    # Reconciliation is not a new authorization: the same request ID remains terminal.
    third = second_gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request,
        authorization=auth,
        admission=_admission(request_id=request_id, auth=auth, adapter_id="fake-adapter"),
        safety=safety,
        snapshot=_snapshot(),
    )
    assert third.status is RealGatewayStatus.BLOCKED
    assert second_adapter.calls == 0
