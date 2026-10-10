from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from core.execution_coordinator import ExecutionCoordinator, ExecutionPlan
from core.live_orchestrator import OrchestrationResult, TradingOrchestrator
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from core.senior_context_cycle import SeniorContextCycle
from core.execution_intent import ExecutionIntent
from core.market_context import MarketContextResult
from execution.gateway import GatewayResult, GatewayStatus
from data.feed import MarketDataRequest
from core.p41_controlled_automation import AutomationCycle, AutomationPolicy
from core.p45_automation_audit import AutomationAuditRecord
from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleBoundary, AutomationLifecycleState
from integration.controlled_automation_service import ControlledAutomationService
from core.p47_automation_closure import AutomationClosureBoundary
from core.p48_automation_outcome import AutomationOutcomeBoundary
from core.p49_outcome_reconciliation import ExternalOutcomeObservation, OutcomeReconciliationBoundary
from core.p50_automation_result_snapshot import AutomationResultSnapshot, AutomationResultSnapshotBoundary
from core.p121_external_order_reconciliation import ExternalOrderQueryPort, ExternalOrderReconciliationBoundary, ExternalOrderStatus
from core.market_data_runtime_state import MarketDataRuntimeState
from core.demo_readiness import DemoReadinessReport
from core.p39_pretrade_risk import RiskAssessment
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleStore, ExecutionLifecycleState


@dataclass(frozen=True)
class RuntimeCycle:
    """Resultado de um ciclo do runtime, sem esconder a decisão."""

    orchestration: OrchestrationResult
    plan: ExecutionPlan | None
    execution: GatewayResult | None
    automation_lifecycle: AutomationLifecycle | None = None
    automation_audit: AutomationAuditRecord | None = None


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

    def __init__(self, *, orchestrator: TradingOrchestrator, coordinator: ExecutionCoordinator, market_data_state: MarketDataRuntimeState | None = None, automation_service: ControlledAutomationService | None = None) -> None:
        if orchestrator is None:
            raise ValueError("orchestrator é obrigatório.")
        if coordinator is None:
            raise ValueError("coordinator é obrigatório.")
        self.orchestrator = orchestrator
        self.coordinator = coordinator
        self.market_data_state = market_data_state
        self.automation_service = automation_service or ControlledAutomationService()

    @staticmethod
    def validate_external_cycle_identity(
        *,
        cycle_id: str,
        external_id: str,
        ledger: ExecutionLedger,
        execution_lifecycle: ExecutionLifecycleStore,
    ) -> tuple[str, object, object]:
        """Validate cycle/external identity before any external side effect."""
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            raise ValueError("cycle_id é obrigatório")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id é obrigatório")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório")
        if not isinstance(execution_lifecycle, ExecutionLifecycleStore):
            raise ValueError("execution_lifecycle é obrigatório")
        matches = ledger.find_by_cycle_id(cycle_id)
        if len(matches) != 1:
            raise ValueError("cycle_id não possui uma identidade de execução única neste runtime.")
        request_id, identity = matches[0]
        if identity.external_id is not None and identity.external_id != external_id.strip():
            raise ValueError("external_id não pertence ao cycle_id informado.")
        execution_record = execution_lifecycle.get(request_id)
        if execution_record is None:
            raise ValueError("request_id não possui ciclo de execução persistido.")
        if execution_record.state not in (
            ExecutionLifecycleState.PENDING,
            ExecutionLifecycleState.ACCEPTED,
            ExecutionLifecycleState.UNKNOWN,
        ):
            raise ValueError("request_id não está em estado de execução reconciliável.")
        return request_id, identity, execution_record

    @staticmethod
    def reconcile_external_cycle(
        *,
        cycle_id: str,
        external_id: str,
        query_port: ExternalOrderQueryPort,
        ledger: ExecutionLedger,
        execution_lifecycle: ExecutionLifecycleStore,
        observed_at: datetime | None = None,
    ) -> AutomationResultSnapshot | None:
        """Reconcile only an execution identity already created by this runtime."""
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            raise ValueError("cycle_id é obrigatório")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id é obrigatório")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório")
        if not isinstance(execution_lifecycle, ExecutionLifecycleStore):
            raise ValueError("execution_lifecycle é obrigatório")
        if not callable(getattr(query_port, "query_order", None)):
            raise ValueError("query_port inválido")
        observed_at = observed_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at deve ser timezone-aware")

        request_id, identity, execution_record = TradingRuntime.validate_external_cycle_identity(
            cycle_id=cycle_id,
            external_id=external_id,
            ledger=ledger,
            execution_lifecycle=execution_lifecycle,
        )
        if identity.status not in (
            ExecutionLedgerStatus.RESERVED,
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.ACCEPTED,
            ExecutionLedgerStatus.RECONCILED_EXECUTED,
            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
        ):
            raise ValueError("cycle_id não está em estado de execução reconciliável.")

        if identity.external_id is None:
            ledger.bind_external_id(request_id, external_id)
            identity = ledger.record_for(request_id)
            assert identity is not None

        observation = query_port.query_order(external_id)
        reconciled = ExternalOrderReconciliationBoundary().reconcile(external_id, observation)
        if reconciled.status in (ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN):
            return None

        executed = reconciled.status is ExternalOrderStatus.EXECUTED
        if identity.status is ExecutionLedgerStatus.RECONCILED_EXECUTED and not executed:
            raise ValueError("reconciliação terminal contraditória para o mesmo external_id.")
        if identity.status is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED and executed:
            raise ValueError("reconciliação terminal contraditória para o mesmo external_id.")
        if identity.status not in (
            ExecutionLedgerStatus.RECONCILED_EXECUTED,
            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
        ):
            ledger.reconcile(request_id, executed=executed)

        if executed:
            if execution_record.state is not ExecutionLifecycleState.ACCEPTED:
                execution_lifecycle.reconcile(
                    request_id,
                    ExecutionLifecycleState.ACCEPTED,
                    updated_at=observed_at,
                    message=reconciled.message,
                )
            terminal = AutomationLifecycleState.COMPLETED
        else:
            execution_lifecycle.reconcile(
                request_id,
                ExecutionLifecycleState.REJECTED,
                updated_at=observed_at,
                message=reconciled.message,
            )
            terminal = AutomationLifecycleState.BLOCKED

        lifecycle = AutomationLifecycle(cycle_id, AutomationLifecycleState.DISPATCHED)
        lifecycle = AutomationLifecycleBoundary().transition(lifecycle, terminal)
        closure = AutomationClosureBoundary().close(lifecycle, closed_at=observed_at)
        trade_outcome = None
        outcome_query = getattr(query_port, "query_trade_outcome", None)
        if executed and callable(outcome_query):
            trade_outcome = outcome_query(external_id)

        confirmed_outcome = (
            trade_outcome is not None
            and getattr(trade_outcome, "closed", False) is True
            and getattr(trade_outcome, "source", None) == "MT5_DEMO_HISTORY"
            and getattr(trade_outcome, "outcome", None) in {"WIN", "LOSS", "DRAW"}
            and isinstance(getattr(trade_outcome, "financial_result", None), (int, float))
            and not isinstance(getattr(trade_outcome, "financial_result", None), bool)
        )
        outcome_observed_at = observed_at
        external_observation = None
        outcome_name = "UNKNOWN"
        financial_result = None
        if confirmed_outcome:
            outcome_observed_at = getattr(trade_outcome, "observed_at", observed_at)
            if (not isinstance(outcome_observed_at, datetime)
                    or outcome_observed_at.tzinfo is None
                    or outcome_observed_at.utcoffset() is None
                    or outcome_observed_at < closure.closed_at):
                confirmed_outcome = False
            else:
                outcome_name = trade_outcome.outcome
                financial_result = float(trade_outcome.financial_result)
                external_observation = ExternalOutcomeObservation(
                    cycle_id=cycle_id,
                    outcome=outcome_name,
                    financial_result=financial_result,
                )
        if not confirmed_outcome:
            outcome_observed_at = observed_at
            outcome_name = "UNKNOWN"
            financial_result = None

        outcome = AutomationOutcomeBoundary().record(
            closure,
            observed_at=outcome_observed_at,
            outcome=outcome_name,
            financial_result=financial_result,
        )
        reconciliation = OutcomeReconciliationBoundary().reconcile(outcome, external_observation)
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
        automation_policy: AutomationPolicy | None = None,
        automation_last_cycle_at: datetime | None = None,
        automation_readiness: DemoReadinessReport | None = None,
        automation_risk_budget: RiskBudgetAssessment | None = None,
        automation_readiness_factory: Callable[[ExecutionIntent, OrchestrationResult], DemoReadinessReport] | None = None,
        automation_risk_budget_factory: Callable[[object, ExecutionIntent, OrchestrationResult], RiskBudgetAssessment] | None = None,
        automation_pretrade_risk_factory: Callable[[object, ExecutionIntent, OrchestrationResult], RiskAssessment] | None = None,
    ) -> RuntimeResult:
        if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles <= 0:
            raise ValueError("max_cycles deve ser um inteiro positivo.")
        if checkpoint_store is not None and not isinstance(checkpoint_store, RuntimeCheckpointStore):
            raise ValueError("checkpoint_store inválido.")
        if checkpoint_store is not None and (not isinstance(session_id, str) or not session_id.strip()):
            raise ValueError("session_id é obrigatório quando checkpoint_store é usado.")
        if request_id_factory is None:
            request_id_factory = lambda index: f"runtime-{index:06d}"
        if automation_policy is not None:
            if not isinstance(automation_policy, AutomationPolicy):
                raise ValueError("automation_policy inválida.")
            if automation_readiness_factory is None and not isinstance(automation_readiness, DemoReadinessReport):
                raise ValueError("automation_readiness ou automation_readiness_factory é obrigatório.")
            if automation_risk_budget_factory is None and not isinstance(automation_risk_budget, RiskBudgetAssessment):
                raise ValueError("automation_risk_budget ou automation_risk_budget_factory é obrigatório.")

        cycles: list[RuntimeCycle] = []
        stopped = False
        stop_reason = None

        for index in range(1, max_cycles + 1):
            automation_lifecycle = None
            automation_audit = None
            automation_request = None

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
                        symbol=request.symbol,
                        timeframe=request.timeframe,
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

            if automation_policy is not None:
                if plan is None:
                    cycle_id = getattr(getattr(orchestration, "senior_context", None), "cycle_id", request_id_factory(index))
                    automation_lifecycle = AutomationLifecycle(cycle_id, AutomationLifecycleState.CREATED)
                    automation_lifecycle = AutomationLifecycleBoundary().transition(
                        automation_lifecycle, AutomationLifecycleState.BLOCKED,
                    )
                    cycles.append(RuntimeCycle(
                        orchestration=orchestration,
                        plan=None,
                        execution=None,
                        automation_lifecycle=automation_lifecycle,
                    ))
                    stopped = True
                    stop_reason = "automação controlada exige decisão EXECUTAR."
                    break

                intent = self.coordinator.build_intent(plan, orchestration=orchestration)
                effective_readiness = (
                    automation_readiness_factory(intent, orchestration)
                    if automation_readiness_factory is not None
                    else automation_readiness
                )
                effective_risk_budget = (
                    automation_risk_budget_factory(operational_state, intent, orchestration)
                    if automation_risk_budget_factory is not None
                    else automation_risk_budget
                )
                effective_pretrade_risk = (
                    automation_pretrade_risk_factory(operational_state, intent, orchestration)
                    if automation_pretrade_risk_factory is not None
                    else None
                )
                if not isinstance(effective_readiness, DemoReadinessReport):
                    effective_readiness = DemoReadinessReport(False, ("prontidão DEMO não configurada.",))
                if not isinstance(effective_risk_budget, RiskBudgetAssessment):
                    effective_risk_budget = RiskBudgetAssessment(
                        decision=BudgetDecision.BLOCKED,
                        projected_loss=0.0,
                        projected_operations=0,
                        reason="orçamento de risco da automação não configurado.",
                    )

                now = getattr(orchestration, "timestamp", datetime.now(timezone.utc))
                effective_senior_context = getattr(orchestration, "senior_context", None)
                automation_cycle_id = effective_senior_context.cycle_id if effective_senior_context is not None else request_id
                automation_result = self.automation_service.admit(
                    policy=automation_policy,
                    cycle=AutomationCycle(cycle_id=automation_cycle_id, requested_at=now),
                    readiness=effective_readiness,
                    risk_budget=effective_risk_budget,
                    pretrade_risk=effective_pretrade_risk,
                    intent=intent,
                    last_cycle_at=automation_last_cycle_at,
                )
                automation_request = automation_result.request
                automation_lifecycle = automation_result.lifecycle
                automation_audit = automation_result.audit
                if not automation_result.admission.admitted or automation_result.handoff is None or not automation_result.handoff.handed_off:
                    stopped = True
                    stop_reason = "; ".join(automation_result.admission.reasons) or "; ".join(
                        automation_result.handoff.reasons if automation_result.handoff is not None else ()
                    ) or "automação controlada bloqueada."
                    cycles.append(RuntimeCycle(
                        orchestration=orchestration,
                        plan=plan,
                        execution=None,
                        automation_lifecycle=automation_lifecycle,
                        automation_audit=automation_audit,
                    ))
                    break
                automation_lifecycle = self.automation_service.mark_dispatched(automation_cycle_id)

            if orchestration.executable:
                execution_result = self.coordinator.execute_plan(
                    plan,
                    orchestration=orchestration,
                    entry_conditions=entry_conditions,
                )
                if automation_policy is not None:
                    if execution_result.status is GatewayStatus.EXECUTION_REJECTED:
                        automation_lifecycle = self.automation_service.block(automation_lifecycle.cycle_id)
                    elif execution_result.status is GatewayStatus.EXECUTOR_ERROR:
                        # External outcome may be uncertain; keep the automation
                        # lifecycle DISPATCHED until explicit reconciliation.
                        pass
                    # An accepted or uncertain dispatch is not a completed operation.
                    # P47/P48/P49 close it only after external reconciliation.
            elif automation_policy is not None:
                automation_lifecycle = AutomationLifecycleBoundary().transition(
                    automation_lifecycle,
                    AutomationLifecycleState.BLOCKED,
                )
            cycles.append(RuntimeCycle(
                orchestration=orchestration,
                plan=plan,
                execution=execution_result,
                automation_lifecycle=automation_lifecycle,
                automation_audit=automation_audit,
            ))

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
