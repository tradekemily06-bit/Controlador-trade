from __future__ import annotations

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderQueryPort,
    ReconciliationResult,
)
from core.p3_execution_reconciliation import ExecutionReconciliationCoordinator


class ExternalExecutionReconciliationService:
    """Query the broker for the exact durable external identity, then reconcile.

    This path is read-only against the broker: it never submits or retries an
    order. The request_id -> external_id binding in the durable ledger is the
    identity boundary.
    """

    def __init__(
        self,
        *,
        coordinator: ExecutionReconciliationCoordinator,
        query_port: ExternalOrderQueryPort,
    ) -> None:
        if not isinstance(coordinator, ExecutionReconciliationCoordinator):
            raise ValueError("coordinator inválido.")
        if not hasattr(query_port, "query_order") or not callable(query_port.query_order):
            raise ValueError("query_port inválido.")
        self._coordinator = coordinator
        self._query_port = query_port

    def reconcile_request(
        self,
        request_id: str,
    ) -> ReconciliationResult:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")

        ledger = self._coordinator._ledger
        external_id = ledger.external_id(request_id)
        if external_id is None:
            raise ValueError(
                "request_id não possui external_id durável; consulta externa segura indisponível."
            )

        observation = self._query_port.query_order(external_id)
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("consulta externa retornou observação inválida.")
        if observation.external_id.strip() != external_id:
            raise ValueError(
                "consulta externa retornou external_id diferente da identidade durável."
            )

        return self._coordinator.reconcile(
            request_id,
            external_id,
            observation,
        )
