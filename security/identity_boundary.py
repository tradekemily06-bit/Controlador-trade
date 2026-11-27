from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentityPolicy:
    """Fail-closed identity policy for the standalone analyst application.

    A configured local identity supports one local runtime only. Remote
    production identity must be asserted by trusted server-side middleware;
    a shared bearer token is an access gate, not a user or tenant identity.
    """

    production_identity_required: bool = True
    real_execution_enabled: bool = False

    def status(self, *, remote_identity_middleware_configured: bool = False) -> dict[str, object]:
        return {
            "runtime_identity": "SINGLE_CONFIGURED_LOCAL_IDENTITY",
            "production_identity": "REQUIRED" if self.production_identity_required else "OPTIONAL",
            "trusted_identity_provider": (
                "MIDDLEWARE_EXPECTED_NOT_VERIFIED"
                if remote_identity_middleware_configured else "NOT_CONFIGURED"
            ),
            "remote_identity_middleware": (
                "CONFIGURED_NOT_RUNTIME_VERIFIED"
                if remote_identity_middleware_configured else "NOT_CONFIGURED"
            ),
            "tenant_claim": "REQUIRED_FOR_REMOTE_ACCESS",
            "tenant_isolation": (
                "TRUSTED_TENANT_CONTEXT_REQUIRED_NOT_RUNTIME_VERIFIED"
                if remote_identity_middleware_configured else "SINGLE_USER_RUNTIME_ONLY"
            ),
            "multi_tenant_isolation": (
                "REQUEST_SCOPE_GUARD_PRESENT_IDENTITY_NOT_RUNTIME_VERIFIED"
                if remote_identity_middleware_configured else "SINGLE_USER_RUNTIME_ONLY"
            ),
            "shared_bearer_token_is_user_identity": False,
            "real_execution": "DISABLED" if not self.real_execution_enabled else "ENABLED",
        }

    def authorize_production_request(self, *, authenticated: bool, tenant_id: str | None) -> bool:
        """Fail closed unless trusted authentication and a tenant are both present."""
        if not self.production_identity_required:
            return True
        return bool(authenticated and isinstance(tenant_id, str) and tenant_id.strip())
