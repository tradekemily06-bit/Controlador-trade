from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitStatus:
    """Deployment-level centralized rate-limit posture."""

    centralized_store_configured: bool = False
    policy_configured: bool = False

    @property
    def ready_for_production(self) -> bool:
        return self.centralized_store_configured and self.policy_configured


def require_centralized_rate_limiting(status: RateLimitStatus | None) -> RateLimitStatus:
    """Fail closed unless centralized production rate limiting is configured."""
    if status is None or not status.ready_for_production:
        raise RuntimeError("centralized production rate limiting is not configured")
    return status
