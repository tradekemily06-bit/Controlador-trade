from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from core.execution_coordinator import ExecutionCoordinator, ExecutionPlan
from core.live_orchestrator import OrchestrationResult, TradingOrchestrator
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from core.senior_context_cycle import SeniorContextCycle
from core.market_context import MarketContextResult
from execution.gateway import GatewayResult
from data.feed import MarketDataRequest
from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleBoundary, AutomationLifecycleState
from core.p47_automation_closure import AutomationClosureBoundary
from core.p48_automation_outcome import AutomationOutcomeBoundary
from core.p49_outcome_reconciliation import OutcomeReconciliationBoundary
from core.p50_automation_result_snapshot import AutomationResultSnapshot, AutomationResultSnapshotBoundary
from core.p121_external_order_reconciliation import ExternalOrderQueryPort, ExternalOrderReconciliationBoundary, ExternalOrderStatus
from core.market_data_runtime_state import MarketDataRuntimeState
from core.p122_broker_market_data import BrokerMarketDataSnapshot


@dataclass(frozen=True)
class RuntimeCycle:
    """Resultado de um ciclo do runtime, sem esconder a decisão."""

    orchestration: OrchestrationResult
    plan: ExecutionPlan | None
    execution: GatewayResult | None


@dataclass(frozen=True)
class RuntimeResult:
    """Resumo imutável de uma execução limitada do runtime."""

    cycles: tuple[RuntimeCycle, ...]
    stopped: bool
    stop_reason: str | None

    @property
    def executed_cycles(self) -> int:
        return sum(c.execution is not None and c.execution.accepted for c in self.cycles)


class TradingRuntime:
    """Executa ciclos controlados do ecossistema sem conhecer corretoras."""

    def __init__(self, *, orchestrator: TradingOrchestrator, coordinator: ExecutionCoordinator, market_data_state: MarketDataRuntimeState | None = None) -> None:
        if orchestrator is None:
            raise ValueError("orchestrator é obrigatório.")
        if coordinator is None:
            raise ValueError("coordinator é obrigatório.")
        self.orchestrator = orchestrator
        self.coordinator = coordinator
        self.market_data_state = market_data_state

    @staticmethod
    def reconcile_external_cycle(
        *,
        cycle_id: str,
        external_id: str,
        query_port: ExternalOrderQueryPort,
        observed_at: datetime | None = None,
    ) -> AutomationResultSnapshot | None:
        """Close factual automation state from an external order observation.

        Broker order status is never converted into WIN/LOSS. Financial outcome
        remains UNKNOWN until an explicit financial observation exists.
        """
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            raise ValueError("cycle_id é obrigatório")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id é obrigatório")
        if not callable(getattr(query_port, "query_order", None)):
            raise ValueError("query_port inválido")
        observed_at = observed_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at deve ser timezone-aware")

        observation = query_port.query_order(external_id)
        reconciled = ExternalOrderReconciliationBoundary().reconcile(external_id, observation)
        if reconciled.status in (ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN):
            return None

        terminal = (
            AutomationLifecycleState.COMPLETED
            if reconciled.status is ExternalOrderStatus.EXECUTED
            else AutomationLifecycleState.BLOCKED
        )
        lifecycle = AutomationLifecycle(cycle_id, AutomationLifecycleState.DISPATCHED)
        lifecycle = AutomationLifecycleBoundary().transition(lifecycle, terminal)
        closure = AutomationClosureBoundary().close(lifecycle, closed_at=observed_at)
        outcome = AutomationOutcomeBoundary().record(
            closure,
            observed_at=observed_at,
            outcome="UNKNOWN",
            financial_result=None,
        )
        reconciliation = OutcomeReconciliationBoundary().reconcile(outcome, None)
        return AutomationResultSnapshotBoundary().compose(closure, outcome, reconciliation)

    def run(
        self,
        request: MarketDataRequest,
        *,
        operational_state,
        market_context: MarketContextResult | None = None,
        senior_context: SeniorContextCycle | None = None,
        amount: float,
        duration_seconds: int,
        max_cycles: int = 1,
        request_id_factory: Callable[[int], str] | None = None,
        confirmed: bool = False,
        filters_ok: bool = True,
        daily_result=None,
        operations_count=None,
        consecutive_losses=None,
        entry_conditions: tuple[str, ...] = (),
        checkpoint_store: RuntimeCheckpointStore | None = None,
        session_id: str | None = None,
    ) -> RuntimeResult:
        if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles <= 0:
            raise ValueError("max_cycles deve ser um inteiro positivo.")
        if checkpoint_store is not None and not isinstance(checkpoint_store, RuntimeCheckpointStore):
            raise ValueError("checkpoint_store inválido.")
        if checkpoint_store is not None and (not isinstance(session_id, str) or not session_id.strip()):
            raise ValueError("session_id é obrigatório quando checkpoint_store é usado.")
        if request_id_factory is None:
            request_id_factory = lambda index: f"runtime-{index:06d}"

        cycles: list[RuntimeCycle] = []
        stopped = False
        stop_reason = None

        for index in range(1, max_cycles + 1):
            orchestration = self.orchestrator.evaluate(
                request,
                operational_state=operational_state,
                market_context=market_context,
                senior_context=senior_context,
                confirmed=confirmed,
                filters_ok=filters_ok,
                daily_result=daily_result,
                operations_count=operations_count,
                consecutive_losses=consecutive_losses,
            )
            if self.market_data_state is not None:
                self.market_data_state.update(
                    BrokerMarketDataSnapshot(
                        symbol=orchestration.market_data.request.symbol,
                        timeframe=orchestration.market_data.request.timeframe,
                        candles=tuple(orchestration.market_data.candles),
                        source=orchestration.market_data.source,
                        received_at=orchestration.timestamp,
                    ),
                    now=orchestration.timestamp,
                )

            plan = None
            execution_result = None
            request_id = None
            if orchestration.executable:
                request_id = request_id_factory(index)
                plan = self.coordinator.build_plan(
                    orchestration,
                    request_id=request_id,
                    amount=amount,
                    duration_seconds=duration_seconds,
                )
                execution_result = self.coordinator.execute_plan(
                    plan,
                    orchestration=orchestration,
                    entry_conditions=entry_conditions,
                )
            cycles.append(RuntimeCycle(orchestration=orchestration, plan=plan, execution=execution_result))

            if checkpoint_store is not None:
                checkpoint_store.save(
                    RuntimeCheckpoint(
                        session_id=session_id,
                        last_cycle=index,
                        last_request_id=request_id,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

            if execution_result is not None and not execution_result.accepted:
                stopped = True
                stop_reason = execution_result.message
                break

        return RuntimeResult(tuple(cycles), stopped, stop_reason)
