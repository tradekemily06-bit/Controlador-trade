from __future__ import annotations

from dataclasses import dataclass
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.external_execution_registry import ExternalExecutionRegistry
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
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
        lifecycle: ExecutionLifecycleStore | None = None,
        external_registry: ExternalExecutionRegistry | None = None,
    ) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if lifecycle is not None and not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle inválido.")
        if external_registry is None:
            external_registry = ExternalExecutionRegistry(
                ledger.path.with_name(f"{ledger.path.stem}.external.json")
            )
        if not isinstance(external_registry, ExternalExecutionRegistry):
            raise ValueError("external_registry inválido.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._external_registry = external_registry
        self._processed_request_ids: set[str] = set(ledger.records())

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if not isinstance(request.amount, (int, float)) or not math.isfinite(request.amount) or request.amount <= 0:
            return False
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return False
        return True

    def execute(
        self,
        *,
        broker: str,
        request_id: str,
        request: ExecutionRequest,
        authorization: RealExecutionAuthorization,
        admission: RealAdmission,
        safety: RealSafetyReport,
    ) -> RealGatewayResult:
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")

        if self._lifecycle is not None:
            current = self._lifecycle.get(request_id)
            if current is not None:
                if current.state is ExecutionLifecycleState.UNKNOWN:
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, "request_id está UNKNOWN; reconciliação explícita obrigatória.")
                if current.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.ACCEPTED):
                    return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já possui ciclo REAL; replay recusado.")
                if current.state is ExecutionLifecycleState.REJECTED:
                    return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já possui ciclo terminal; replay recusado.")

        current_status = self._ledger.status(request_id)
        if current_status is not None:
            self._processed_request_ids.add(request_id)
            if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
                )
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

        try:
            self._ledger.reserve(request_id)
            if self._lifecycle is not None:
                from datetime import datetime, timezone
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.PENDING,
                        datetime.now(timezone.utc),
                        "execução REAL iniciada",
                    )
                )
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")

        try:
            result = self._gateway.execute(broker, request)
        except Exception as exc:
            try:
                self._ledger.mark_unknown(request_id)
                if self._lifecycle is not None:
                    from datetime import datetime, timezone
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id,
                            ExecutionLifecycleState.UNKNOWN,
                            datetime.now(timezone.utc),
                            f"resultado REAL incerto: {type(exc).__name__}: {exc}",
                        )
                    )
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

        if result.execution is None:
            try:
                self._ledger.mark_unknown(request_id)
                if self._lifecycle is not None:
                    from datetime import datetime, timezone
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
                self._ledger.mark_unknown(request_id)
                if self._lifecycle is not None:
                    from datetime import datetime, timezone
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id,
                            ExecutionLifecycleState.UNKNOWN,
                            datetime.now(timezone.utc),
                            result.execution.message,
                        )
                    )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    f"resultado REAL incerto e persistência falhou: {exc}",
                    result.execution,
                )
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                result.execution.message,
                result.execution,
            )

        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
                if self._lifecycle is not None:
                    from datetime import datetime, timezone
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id,
                            ExecutionLifecycleState.REJECTED,
                            datetime.now(timezone.utc),
                            result.execution.message,
                        )
                    )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    f"ordem rejeitada, mas persistência do estado falhou: {exc}",
                    result.execution,
                )
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
                if self._lifecycle is not None:
                    from datetime import datetime, timezone
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id,
                            ExecutionLifecycleState.UNKNOWN,
                            datetime.now(timezone.utc),
                            "aceite REAL sem external_id",
                        )
                    )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    f"aceite REAL sem external_id e persistência falhou: {exc}",
                    result.execution,
                )
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                "aceite REAL sem external_id; reconciliação explícita necessária.",
                result.execution,
            )

        try:
            self._external_registry.bind(request_id, broker, result.execution.external_id)
            self._ledger.mark_accepted(request_id)
        except (OSError, ValueError) as exc:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"ordem REAL aceita, mas persistência primária falhou: {exc}",
                result.execution,
            )

        if self._lifecycle is not None:
            try:
                from datetime import datetime, timezone
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.ACCEPTED,
                        datetime.now(timezone.utc),
                        result.execution.message,
                    )
                )
            except (OSError, ValueError) as exc:
                # Ledger + external binding are already durable. Do not downgrade
                # the authoritative execution state to UNKNOWN merely because the
                # projection store failed. Recovery must repair the projection.
                return RealGatewayResult(
                    RealGatewayStatus.ADMITTED,
                    f"ordem REAL aceita; projeção Lifecycle requer reparo: {exc}",
                    result.execution,
                )
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def reconcile_unknown(
        self,
        request_id: str,
        *,
        observation: ExternalOrderObservation,
    ) -> None:
        """Reconcile only from explicit external evidence; never resubmits."""
        if self._ledger.status(request_id) not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("evidência externa obrigatória para reconciliação.")
        binding = self._external_registry.get(request_id)
        if binding is None:
            raise ValueError(
                "não existe external_id durável para vincular a evidência externa."
            )
        _broker, external_id = binding
        if observation.external_id.strip() != external_id:
            raise ValueError("external_id da evidência não corresponde ao request_id.")
        if observation.status not in (
            ExternalOrderStatus.EXECUTED,
            ExternalOrderStatus.NOT_EXECUTED,
        ):
            raise ValueError(
                "evidência externa ainda é PENDING/UNKNOWN; estado permanece incerto."
            )

        from datetime import datetime, timezone
        executed = observation.status is ExternalOrderStatus.EXECUTED
        self._ledger.reconcile(request_id, executed=executed)
        if self._lifecycle is not None:
            self._lifecycle.reconcile(
                request_id,
                ExecutionLifecycleState.ACCEPTED if executed else ExecutionLifecycleState.REJECTED,
                updated_at=datetime.now(timezone.utc),
                message=observation.message,
            )
