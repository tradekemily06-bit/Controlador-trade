from __future__ import annotations

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
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
        query_port: object,
    ) -> None:
        if not isinstance(coordinator, ExecutionReconciliationCoordinator):
            raise ValueError("coordinator inválido.")
        # Capability is checked at the specific recovery operation. Adapters
        # without read-only lookup can therefore exist safely; invoking an
        # unsupported recovery path fails closed instead of at construction.
        if query_port is None:
            raise ValueError("query_port inválido.")
        self._coordinator = coordinator
        self._query_port = query_port

    def reconcile_request(
        self,
        request_id: str,
    ) -> ReconciliationResult:
        if not isinstance(request_id, str) or not request_id.strip() or request_id != request_id.strip():
            raise ValueError("request_id inválido ou não canônico.")

        external_id = self._coordinator.external_id_for(request_id)
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


    def reconcile_request_by_request_id(
        self,
        request_id: str,
    ) -> ReconciliationResult:
        """Recover a lost external_id through a broker's read-only request-id query.

        This is intentionally opt-in: adapters that do not explicitly expose
        query_order_by_request_id cannot use this path. No order submission is
        ever attempted here.
        """
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")

        query = self._query_port
        method = getattr(query, "query_order_by_request_id", None)
        if not callable(method):
            raise ValueError(
                "o adapter não oferece consulta externa somente-leitura por request_id; "
                "reconciliação automática não é segura neste cenário."
            )

        # Identity discovery must be serialized with REAL dispatch. Otherwise a
        # recovery worker could bind an external identity while a live execution
        # is still between the final authority check and the broker response.
        with self._coordinator.request_execution_lock(request_id):
            observation = method(request_id.strip())
            if not isinstance(observation, ExternalOrderObservation):
                raise ValueError("consulta externa por request_id retornou observação inválida.")
            if not isinstance(observation.external_id, str) or not observation.external_id.strip():
                raise ValueError("consulta externa por request_id não retornou external_id.")
            durable_external_id = self._coordinator.external_id_for(request_id)
            if durable_external_id is not None and observation.external_id.strip() != durable_external_id:
                raise ValueError(
                    "consulta por request_id retornou external_id diferente da identidade durável."
                )

            if durable_external_id is None:
                self._coordinator._bind_external_id_locked(request_id, observation.external_id.strip())

        # Reconciliation acquires the same lock again and revalidates the
        # observation against the authoritative post-query state, preventing a
        # stale observation from finalizing a concurrently changed request.
        return self._coordinator.reconcile(
            request_id,
            observation.external_id.strip(),
            observation,
        )
