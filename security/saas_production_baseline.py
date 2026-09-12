from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SaaSProductionSecurityState:
    """Provider-neutral fail-closed gate for protected SaaS production use.

    These controls are deployment prerequisites. The core must not silently
    substitute fake authentication, in-memory tenant isolation, or local-only
    controls for production guarantees.
    """

    trusted_identity: bool = False
    tenant_isolated_durable_storage: bool = False
    secure_transport: bool = False
    secret_management: bool = False
    durable_audit: bool = False
    centralized_rate_limiting: bool = False
    real_execution_enabled: bool = False

    @property
    def ready(self) -> bool:
        return all(
            (
                self.trusted_identity,
                self.tenant_isolated_durable_storage,
                self.secure_transport,
                self.secret_management,
                self.durable_audit,
                self.centralized_rate_limiting,
            )
        ) and not self.real_execution_enabled

    def status(self) -> dict[str, object]:
        return {
            "status": "READY" if self.ready else "BLOCKED",
            "trusted_identity": self.trusted_identity,
            "tenant_isolated_durable_storage": self.tenant_isolated_durable_storage,
            "secure_transport": self.secure_transport,
            "secret_management": self.secret_management,
            "durable_audit": self.durable_audit,
            "centralized_rate_limiting": self.centralized_rate_limiting,
            "real_execution": "DISABLED" if not self.real_execution_enabled else "ENABLED",
        }

    def authorize_protected_operation(self) -> bool:
        """Allow protected production work only when every prerequisite is true."""

        return self.ready
