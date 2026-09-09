from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.execution_coordinator import ExecutionCoordinator, ExecutionPlan
from core.live_orchestrator import OrchestrationResult, TradingOrchestrator
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
        return sum(
            c.execution is not None and c.execution.accepted
            for c in self.cycles
        )


class TradingRuntime:
    """Executa ciclos controlados do ecossistema sem conhecer corretoras."""

    def __init__(
        self,
        *,
        orchestrator: TradingOrchestrator,
        coordinator: ExecutionCoordinator,
    ) -> None:
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
    ) -> RuntimeResult:
        if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles <= 0:
            raise ValueError("max_cycles deve ser um inteiro positivo.")
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
                confirmed=confirmed,
                filters_ok=filters_ok,
                daily_result=daily_result,
                operations_count=operations_count,
                consecutive_losses=consecutive_losses,
            )
            plan = None
            execution_result = None
            if orchestration.executable:
                plan = self.coordinator.build_plan(
                    orchestration,
                    request_id=request_id_factory(index),
                    amount=amount,
                    duration_seconds=duration_seconds,
                )
                execution_result = self.coordinator.execute_plan(
                    plan,
                    orchestration=orchestration,
                    entry_conditions=entry_conditions,
                )
            cycles.append(
                RuntimeCycle(
                    orchestration=orchestration,
                    plan=plan,
                    execution=execution_result,
                )
            )

            if execution_result is not None and not execution_result.accepted:
                stopped = True
                stop_reason = execution_result.message
                break

        return RuntimeResult(tuple(cycles), stopped, stop_reason)
