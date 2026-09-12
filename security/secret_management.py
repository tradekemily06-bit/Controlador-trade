from __future__ import annotations

from abc import ABC, abstractmethod


class SecretManagementBoundary(ABC):
    """Provider-neutral boundary for production secret retrieval.

    Production implementations must retrieve secrets from an external secret
    manager rather than source files, repository configuration, or logs.
    """

    production_ready: bool = False

    @abstractmethod
    def get_secret(self, name: str) -> str:
        raise NotImplementedError

    @property
    def ready_for_production(self) -> bool:
        return bool(self.production_ready)


def require_secret_manager(manager: SecretManagementBoundary | None) -> SecretManagementBoundary:
    """Fail closed when production secret management is not configured."""
    if manager is None or not manager.ready_for_production:
        raise RuntimeError("production secret management is not configured")
    return manager
