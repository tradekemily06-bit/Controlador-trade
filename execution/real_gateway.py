from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
import threading

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.p119_release_closure import RealReleaseClosure
from core.kill_switch import KillSwitch
from execution.adapter_gateway import BrokerAdapterGateway, _REAL_DISPATCH_CAPABILITY
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore, LIFECYCLE_RECOVERY_CAPABILITY
from execution.execution_coordination import ExecutionCoordinationLock
from execution.real_reconciliation import RealReconciliationPort, ReconciliationOutcome, validate_observation
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class RealGatewayStatus(str):
    ADMITTED = "ADMITTED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RealGatewayResult:
    status: str
    message: str
    execution: ExecutionResult | None = None


class RealExecutionGateway:
    """The only REAL dispatch boundary. Broker details stay behind BrokerAdapterGateway."""

    def __init__(
        self,
        adapter_gateway: BrokerAdapterGateway,
        ledger: ExecutionLedger,
        lifecycle: ExecutionLifecycleStore,
        kill_switch: KillSwitch,
    ) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle é obrigatório para execução REAL.")
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch é obrigatório para execução REAL.")
        # REAL must never be composed with an ephemeral kill switch. Its
        # durable state and coordination lock must exist, and the coordination
        # identity must be the same one protecting the REAL Ledger critical
        # section. Otherwise a second process could activate the switch while
        # this gateway is dispatching under a different lock.
        if not kill_switch.is_durable:
            raise ValueError("REAL exige kill switch durável e coordenado.")
        if kill_switch.coordination_path != ledger.path:
            raise ValueError("kill switch REAL deve compartilhar a coordenação do Ledger.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._coordination = ExecutionCoordinationLock(ledger.path)
        self._kill_switch = kill_switch
        # The filesystem lock serializes independent threads/processes, but POSIX
        # flock can be reacquired by the same process. A callback from an adapter
        # or reconciler into this gateway would otherwise deadlock or recursively
        # dispatch a second REAL order. Keep the REAL gateway explicitly
        # non-reentrant per thread.
        self._reentry = threading.local()

    def _reentry_active(self) -> bool:
        return bool(getattr(self._reentry, "active", False))

    @contextmanager
    def _entry_guard(self, operation: str):
        if self._reentry_active():
            raise RuntimeError(f"reentrada proibida na fronteira REAL durante {operation}.")
        self._reentry.active = True
        try:
            yield
        finally:
            self._reentry.active = False

    @staticmethod
    def _valid_request(request_id: str, request: ExecutionRequest) -> bool:
        if not isinstance(request_id, str) or not request_id.strip():
            return False
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if request.request_id is not None and (
            not isinstance(request.request_id, str)
            or request.request_id.strip() != request_id.strip()
        ):
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if not isinstance(request.amount, (int, float)) or not math.isfinite(request.amount) or request.amount <= 0:
            return False
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return False
        return True

    def _recovery_safe(self) -> bool:
        """Block new REAL dispatch when any durable execution state needs repair."""
        try:
            lifecycle = self._lifecycle.records()
            ledger_ids = self._ledger.records()
            ledger_states = {request_id: self._ledger.status(request_id) for request_id in ledger_ids}
        except (OSError, ValueError):
            return False

        lifecycle_by_id = {record.request_id: record for record in lifecycle}
        if any(record.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN) for record in lifecycle):
            return False

        if set(lifecycle_by_id) != set(ledger_states):
            return False

        for request_id, status in ledger_states.items():
            record = lifecycle_by_id[request_id]
            # Every durable execution state must remain cryptographically bound
            # to the original request intent. A terminal record without
            # context/fingerprint may look harmless, but it cannot be
            # independently reconciled after a crash; fail closed before any
            # unrelated REAL dispatch is allowed to continue.
            context = self._ledger.context(request_id)
            fingerprint = self._ledger.fingerprint(request_id)
            if not isinstance(context, dict) or not context or not isinstance(fingerprint, str) or not fingerprint.strip():
                return False
            if context.get("request_id") != request_id:
                return False
            if status is ExecutionLedgerStatus.ACCEPTED:
                if record.state is not ExecutionLifecycleState.ACCEPTED:
                    return False
                if self._ledger.external_id(request_id) is None:
                    return False
            if status is ExecutionLedgerStatus.RECONCILED_EXECUTED:
                if record.state is not ExecutionLifecycleState.ACCEPTED:
                    return False
                if self._ledger.external_id(request_id) is None:
                    return False
            if status is ExecutionLedgerStatus.REJECTED and record.state is not ExecutionLifecycleState.REJECTED:
                return False
            if status is ExecutionLedgerStatus.RECONCILED_EXECUTED and record.state is not ExecutionLifecycleState.ACCEPTED:
                return False
            if status is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED and record.state is not ExecutionLifecycleState.REJECTED:
                return False
            if status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                return False

        return True

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport, release: RealReleaseClosure) -> RealGatewayResult:
        # Recovery assessment, reservation and the external side effect share
        # one process/host coordination boundary. This prevents a concurrent
        # recovery or second REAL request from observing a transient safe state.
        # The entry guard additionally prevents same-thread callbacks from an
        # adapter/reconciler from deadlocking or recursively dispatching REAL.
        if self._reentry_active():
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "reentrada proibida na fronteira REAL durante execução externa.",
            )
        with self._entry_guard("execute"), self._coordination.acquire():
            return self._execute_locked(
                broker=broker,
                request_id=request_id,
                request=request,
                authorization=authorization,
                admission=admission,
                safety=safety,
                release=release,
            )

    def _execute_locked(self, *, broker: str, request_id: str, request: ExecutionRequest,
                        authorization: RealExecutionAuthorization, admission: RealAdmission,
                        safety: RealSafetyReport, release: RealReleaseClosure) -> RealGatewayResult:
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        # Canonicalize the identity before touching durable state or the broker.
        # Otherwise "req-1" and " req-1 " could become distinct local reservations
        # while a broker normalizes them to the same external correlation key.
        request_id = request_id.strip()
        if isinstance(request, ExecutionRequest) and request.request_id is not None:
            if not isinstance(request.request_id, str) or not request.request_id.strip():
                return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id da request inválido.")
            request = replace(request, request_id=request.request_id.strip())
        if type(release) is not RealReleaseClosure or not release.released:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "release REAL não está formalmente fechado.")
        if type(authorization) is not RealExecutionAuthorization or not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if type(admission) is not RealAdmission or not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if type(safety) is not RealSafetyReport or not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._kill_switch.allows_execution():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "kill switch ativo no momento da execução REAL.")
        if not self._valid_request(request_id, request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        # A request already recorded in an uncertain state must report UNKNOWN
        # for that same request_id. Only genuinely new requests are blocked by
        # unrelated recovery debt elsewhere in the execution stores.
        current_status = self._ledger.status(request_id)
        if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
            )
        if current_status is not None:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")
        if not self._recovery_safe():
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "estado de execução exige reconciliação; novo despacho REAL bloqueado.",
            )
        if request.request_id is None:
            # Bind the canonical ledger identity before correlation is computed.
            # The broker-side recovery key must be derived from the exact durable
            # request_id that will be reserved, never from an unbound request.
            request = replace(request, request_id=request_id)
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")
        registered_adapter_id = self._gateway.adapter_id(broker)
        if not isinstance(registered_adapter_id, str) or not registered_adapter_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "adapter REAL sem identidade registrada.")
        if registered_adapter_id.strip() != authorization.adapter_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "adapter da requisição difere da autorização.")

        try:
            correlation = self._gateway.correlation_for(broker, request)
            # REAL recovery requires a deterministic provider-side correlation.
            # Without it, a later read could match an unrelated execution with
            # the same symbol/side/amount. Never create a REAL request that
            # cannot carry a durable, broker-searchable identity.
            if not isinstance(correlation, str) or not correlation.strip():
                return RealGatewayResult(
                    RealGatewayStatus.BLOCKED,
                    "adapter REAL sem correlation determinística para reconciliação; despacho bloqueado.",
                )
            correlation = correlation.strip()
            self._ledger.reserve(
                request_id,
                context={
                    "broker": broker.strip().lower(),
                    "adapter_id": registered_adapter_id.strip(),
                    "symbol": request.symbol.strip(),
                    "side": request.signal.value,
                    "amount": float(request.amount),
                    "duration_seconds": int(request.duration_seconds),
                    "request_id": request_id,
                    "correlation": correlation,
                    # Provider is bound to the authorized broker identity so
                    # read-side evidence from another provider cannot close
                    # this request accidentally.
                    "provider": broker.strip().lower(),
                },
            )
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id,
                    ExecutionLifecycleState.PENDING,
                    datetime.now(timezone.utc),
                    "execução REAL reservada; despacho externo ainda não confirmado.",
                )
            )
        except (OSError, ValueError) as exc:
            # If the ledger reservation succeeded but its lifecycle marker did not,
            # never proceed to an external side effect. Marking UNKNOWN is the
            # safest durable outcome; recovery will detect any cross-store gap.
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"reserva REAL persistida, mas ciclo de execução não pôde ser persistido: {exc}",
            )

        if not self._kill_switch.allows_execution():
            try:
                self._ledger.mark_rejected(request_id)
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, datetime.now(timezone.utc), "kill switch ativado antes do dispatch REAL"))
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"kill switch bloqueou o dispatch, mas a rejeição não pôde ser persistida: {exc}")
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "kill switch ativado antes do dispatch REAL.")

        try:
            result = self._gateway.execute_real(
                broker, request, capability=_REAL_DISPATCH_CAPABILITY
            )
        except Exception as exc:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            try:
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.UNKNOWN,
                        datetime.now(timezone.utc),
                        f"resultado REAL incerto: {type(exc).__name__}: {exc}",
                    )                )
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

        if result.execution is None:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            try:
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.UNKNOWN,
                        datetime.now(timezone.utc),
                        result.message,
                    )
                )
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if result.execution.uncertain:
            try:
                if result.execution.external_id:
                    self._ledger.bind_external_id(request_id, result.execution.external_id)
                self._ledger.mark_unknown(request_id)
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.UNKNOWN,
                        datetime.now(timezone.utc),
                        result.execution.message,
                    )
                )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto e persistência falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.execution.message, result.execution)

        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.REJECTED,
                        datetime.now(timezone.utc),
                        result.execution.message,
                    )
                )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        # An accepted REAL result without a durable broker/exchange reference is
        # ambiguous: the external order may exist but cannot be safely reconciled.
        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.UNKNOWN,
                        datetime.now(timezone.utc),
                        "aceite REAL sem external_id; reconciliação explícita necessária.",
                    )
                )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            self._ledger.bind_external_id(request_id, result.execution.external_id)
            self._ledger.mark_accepted(request_id)
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id,
                    ExecutionLifecycleState.ACCEPTED,
                    datetime.now(timezone.utc),
                    result.execution.message,
                )
            )
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {exc}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def recover_lifecycle_from_durable_rejection(self, request_id: str) -> None:
        """Repair Lifecycle from durable local rejection without external I/O or replay."""
        with self._entry_guard("recovery de rejeição"), self._coordination.acquire():
            current = self._ledger.status(request_id)
            if current not in (
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                raise ValueError("Ledger não contém rejeição durável recuperável.")
            lifecycle = self._lifecycle.get(request_id)
            if lifecycle is not None and lifecycle.state is ExecutionLifecycleState.REJECTED:
                return
            if lifecycle is not None and lifecycle.state not in (
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.UNKNOWN,
            ):
                raise ValueError("Lifecycle não está em estado recuperável.")
            message = "Lifecycle recuperado a partir da rejeição durável do Ledger; nenhum dispatch adicional permitido."
            if lifecycle is None:
                self._lifecycle.reconcile_missing(
                    request_id, ExecutionLifecycleState.REJECTED,
                    updated_at=datetime.now(timezone.utc), message=message, capability=LIFECYCLE_RECOVERY_CAPABILITY,
                )
            else:
                self._lifecycle.reconcile_pending(
                    request_id, ExecutionLifecycleState.REJECTED,
                    updated_at=datetime.now(timezone.utc), message=message,
                    capability=LIFECYCLE_RECOVERY_CAPABILITY,
                )

    def reconcile_unknown(self, request_id: str, *, reconciler: RealReconciliationPort) -> None:
        """Reconcile UNKNOWN/RESERVED from read-only external broker evidence.

        Reconciliation never redispatches the request. A naked executed=True/False
        is deliberately not accepted because it is not evidence of broker state.
        """
        with self._entry_guard("reconciliação"), self._coordination.acquire():
            self._reconcile_unknown_locked(request_id, reconciler=reconciler)

    def _reconcile_unknown_locked(
        self,
        request_id: str,
        *,
        reconciler: RealReconciliationPort,
    ) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        ledger_status = self._ledger.status(request_id)
        lifecycle = self._lifecycle.get(request_id)

        # A durable local rejection is already conclusive evidence that this
        # gateway did not authorize a dispatch. Repairing only the local
        # Lifecycle must not depend on a broker query that can fail or lie.
        if ledger_status in (
            ExecutionLedgerStatus.ACCEPTED,
            ExecutionLedgerStatus.RECONCILED_EXECUTED,
        ) and self._ledger.external_id(request_id) is not None:
            # A crash can happen after the Ledger terminal state is durable but
            # before Lifecycle becomes terminal. The Ledger already contains the
            # broker identity, so no new broker query or dispatch is necessary.
            if lifecycle is not None and lifecycle.state is ExecutionLifecycleState.ACCEPTED:
                return
            if lifecycle is not None and lifecycle.state not in (
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.UNKNOWN,
            ):
                raise ValueError("ciclo de execução não está em estado recuperável.")
            message = "Lifecycle recuperado a partir de aceite durável do Ledger; nenhum dispatch ou consulta externa necessária."
            if lifecycle is None:
                self._lifecycle.reconcile_missing(
                    request_id,
                    ExecutionLifecycleState.ACCEPTED,
                    updated_at=datetime.now(timezone.utc),
                    message=message,
                    capability=LIFECYCLE_RECOVERY_CAPABILITY,
                )
            elif lifecycle.state is ExecutionLifecycleState.PENDING:
                self._lifecycle.reconcile_pending(
                    request_id,
                    ExecutionLifecycleState.ACCEPTED,
                    updated_at=datetime.now(timezone.utc),
                    message=message,
                    capability=LIFECYCLE_RECOVERY_CAPABILITY,
                )
            else:
                self._lifecycle.reconcile(
                    request_id,
                    ExecutionLifecycleState.ACCEPTED,
                    updated_at=datetime.now(timezone.utc),
                    message=message,
                )
            return

        if ledger_status in (
            ExecutionLedgerStatus.REJECTED,
            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
        ):
            if lifecycle is not None and lifecycle.state is ExecutionLifecycleState.REJECTED:
                return
            if lifecycle is not None and lifecycle.state not in (
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.UNKNOWN,
            ):
                raise ValueError("ciclo de execução não está em estado reconciliável.")
            message = "Lifecycle reparado a partir de rejeição durável local; nenhum dispatch ou consulta externa necessária."
            if lifecycle is None:
                self._lifecycle.reconcile_missing(
                    request_id,
                    ExecutionLifecycleState.REJECTED,
                    updated_at=datetime.now(timezone.utc),
                    message=message,
                    capability=LIFECYCLE_RECOVERY_CAPABILITY,
                )
            else:
                self._lifecycle.reconcile_pending(
                    request_id,
                    ExecutionLifecycleState.REJECTED,
                    updated_at=datetime.now(timezone.utc),
                    message=message,
                    capability=LIFECYCLE_RECOVERY_CAPABILITY,
                )
            return

        if reconciler is None or not callable(getattr(reconciler, "lookup", None)):
            raise ValueError("reconciler REAL somente leitura é obrigatório.")

        context = self._ledger.context(request_id)
        fingerprint = self._ledger.fingerprint(request_id)
        if not isinstance(context, dict) or not context or not isinstance(fingerprint, str) or not fingerprint.strip():
            raise ValueError(
                "reconciliação REAL exige context/fingerprint duráveis; estado legado sem intenção persistida permanece bloqueado."
            )
        if context.get("request_id") != request_id:
            raise ValueError("context REAL não corresponde ao request_id reconciliado.")

        observation = reconciler.lookup(request_id)
        if not validate_observation(request_id, observation):
            raise ValueError("evidência externa de reconciliação inválida ou contraditória.")

        if observation.executed:
            expected_symbol = context.get("symbol")
            if not isinstance(expected_symbol, str) or not expected_symbol.strip() or observation.symbol.strip() != expected_symbol.strip():
                raise ValueError("evidência externa não corresponde ao símbolo persistido da request.")
            side_map = {"COMPRA": "BUY", "VENDA": "SELL", "BUY": "BUY", "SELL": "SELL"}
            expected_side = side_map.get(str(context.get("side", "")).strip().upper())
            observed_side = side_map.get(observation.side.strip().upper())
            if expected_side is None or observed_side != expected_side:
                raise ValueError("evidência externa não corresponde ao lado persistido da request.")
            expected_amount = context.get("amount")
            if not isinstance(expected_amount, (int, float)) or isinstance(expected_amount, bool) or not math.isfinite(float(expected_amount)):
                raise ValueError("context REAL possui amount inválido.")
            if not math.isclose(float(observation.amount), float(expected_amount), rel_tol=0.0, abs_tol=1e-9):
                raise ValueError("evidência externa não corresponde ao amount persistido da request.")
            expected_provider = context.get("provider", context.get("broker"))
            if not isinstance(expected_provider, str) or not expected_provider.strip():
                raise ValueError("context REAL possui provider inválido.")
            if observation.provider.strip().lower() != expected_provider.strip().lower():
                raise ValueError("evidência externa não corresponde ao provider/broker autorizado.")
            expected_correlation = context.get("correlation")
            if not isinstance(expected_correlation, str) or not expected_correlation.strip():
                raise ValueError("context REAL exige correlation persistida.")
            if observation.correlation.strip() != expected_correlation.strip():
                raise ValueError("evidência externa não corresponde à correlation persistida da request.")

        outcome = observation.effective_outcome
        # Only definitive broker answers may close UNKNOWN. "Not found", delayed
        # visibility, query failure and ambiguity are deliberately non-terminal.
        if outcome in (
            ReconciliationOutcome.NOT_FOUND,
            ReconciliationOutcome.NOT_VISIBLE_YET,
            ReconciliationOutcome.QUERY_FAILED,
            ReconciliationOutcome.AMBIGUOUS,
        ):
            return
        if outcome not in (
            ReconciliationOutcome.EXECUTED,
            ReconciliationOutcome.NOT_EXECUTED,
        ):
            raise ValueError("resultado de reconciliação desconhecido.")
        executed = outcome is ReconciliationOutcome.EXECUTED
        ledger_status = self._ledger.status(request_id)
        lifecycle = self._lifecycle.get(request_id)
        desired_ledger = (
            ExecutionLedgerStatus.RECONCILED_EXECUTED
            if executed
            else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
        )
        desired_lifecycle = (
            ExecutionLifecycleState.ACCEPTED
            if executed
            else ExecutionLifecycleState.REJECTED
        )

        terminal_status = (
            ExecutionLedgerStatus.ACCEPTED
            if executed
            else ExecutionLedgerStatus.REJECTED
        )
        durable_external_id = self._ledger.external_id(request_id)
        if executed:
            if not isinstance(observation.external_id, str) or not observation.external_id.strip():
                raise ValueError("reconciliação EXECUTED exige external_id válido na evidência.")
            if observation.external_id_kind.value == "UNKNOWN":
                raise ValueError("reconciliação EXECUTED exige tipo explícito da identidade externa.")
            if durable_external_id is not None and observation.external_id != durable_external_id:
                raise ValueError("external_id observado difere da identidade externa durável.")
            # A crash can occur after the broker accepts an order but before the
            # local external_id bind is durable. In that case the read-only broker
            # observation is the authoritative source for recovering the missing
            # local identity; it is never a new dispatch.

        if ledger_status not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
            terminal_status,
            desired_ledger,
        ):
            raise ValueError("request_id não está em estado reconciliável.")

        now = observation.observed_at
        lifecycle_missing = lifecycle is None

        if lifecycle is not None and lifecycle.state not in (
            ExecutionLifecycleState.UNKNOWN,
            ExecutionLifecycleState.PENDING,
            desired_lifecycle,
        ):
            raise ValueError("ciclo de execução não está em estado reconciliável.")

        if ledger_status is not desired_ledger:
            self._ledger.reconcile(request_id, executed=executed, external_id=observation.external_id if executed else None)
            ledger_status = desired_ledger

        if lifecycle_missing:
            self._lifecycle.reconcile_missing(
                request_id,
                desired_lifecycle,
                updated_at=now,
                message=(
                    "ciclo criado durante reconciliação baseada em evidência externa "
                    f"somente leitura ({observation.source}); nenhum replay permitido."
                ),
                capability=LIFECYCLE_RECOVERY_CAPABILITY,
            )
            return

        if lifecycle.state is desired_lifecycle:
            return

        if lifecycle.state is ExecutionLifecycleState.PENDING and ledger_status is desired_ledger:
            self._lifecycle.reconcile_pending(
                request_id,
                desired_lifecycle,
                updated_at=now,
                message=(
                    "ciclo sincronizado após janela de crash usando evidência externa "
                    f"somente leitura ({observation.source})."
                ),
                capability=LIFECYCLE_RECOVERY_CAPABILITY,
            )
        elif lifecycle.state is ExecutionLifecycleState.UNKNOWN:
            self._lifecycle.reconcile(
                request_id,
                desired_lifecycle,
                updated_at=now,
                message=(
                    "reconciliação REAL baseada em evidência externa somente leitura "
                    f"({observation.source})."
                ),
            )
        else:
            raise ValueError("Ledger e Lifecycle não formam uma combinação reconciliável.")
