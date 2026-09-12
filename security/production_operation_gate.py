from __future__ import annotations

from dataclasses import dataclass

from security.request_context import ProductionRequestContext, require_production_context
from storage.production_boundary import ProductionStoragePolicy


@dataclass(frozen=True)
class ProductionOperationGate:
    """Provider-neutral gate for protected production operations.

    The gate only authorizes a request when trusted identity/tenant context and
    explicitly ready durable production storage are both present. It does not
    authorize REAL trading or perform any external operation.
    """

    storage: ProductionStoragePolicy

    def authorize(
        self,
        *,
        subject_id: str | None,
        tenant_id: str | None,
    ) -> ProductionRequestContext:
        context = require_production_context(subject_id=subject_id, tenant_id=tenant_id)
        if not self.storage.authorize_write(
            authenticated=context.is_valid(),
            tenant_id=context.tenant_id,
        ):
            raise PermissionError("production storage is not ready")
        return context

    def status(self) -> dict[str, object]:
        storage = self.storage.status()
        return {
            "authorized": False,
            "storage_state": storage["state"],
            "real_execution": "DESABILITADO",
        }
