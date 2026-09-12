from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentityPolicy:
    """Provider-neutral production identity boundary.

    The application never implements passwords, sessions, tokens, or login flows here.
    A trusted deployment identity provider must supply an authenticated subject and tenant.
    """

    production_identity_required: bool = True
    real_execution_enabled: bool = False

    def status(self) -> dict[str, object]:
        return {
            "production_identity": "REQUIRED" if self.production_identity_required else "OPTIONAL",
            "trusted_identity_provider": "NOT_CONFIGURED",
            "tenant_isolation": "DEPLOYMENT_BOUNDARY",
            "real_execution": "DISABLED" if not self.real_execution_enabled else "ENABLED",
        }

    def authorize_production_request(self, *, authenticated: bool, tenant_id: str | None) -> bool:
        """Fail closed for production requests until a trusted identity boundary is present."""
        if not self.production_identity_required:
            return True
        return bool(authenticated and tenant_id and tenant_id.strip())
