from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from core.execution_coordinator import ExecutionCoordinator, ExecutionPlan
from core.live_orchestrator import OrchestrationResult, TradingOrchestrator
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from core.senior_context_cycle import SeniorContextCycle
from execution.gateway import GatewayResult
from data.feed import MarketDataRequest


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

    def __init__(self, *, orchestrator: TradingOrchestrator, coordinator: ExecutionCoordinator) -> None:
        if orchestrator is None:
            raise ValueError("orchestrator é obrigatório.")
        if coordinator is None:
            raise ValueError("coordinator é obrigatório.")
        self.orchestrator = orchestrator
        self.coordinator = coordinator

    def run(
        self,
        request: MarketDataRequest,
        *,
        operational_state,
        market_context,
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
            cycle_id = str(uuid4())
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
                cycle_id=cycle_id,
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
                        last_decision_id=getattr(orchestration, "decision_id", None) or None,
                        last_cycle_id=getattr(orchestration, "cycle_id", None) or None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

            if execution_result is not None and not execution_result.accepted:
                stopped = True
                stop_reason = execution_result.message
                break

        return RuntimeResult(tuple(cycles), stopped, stop_reason)
