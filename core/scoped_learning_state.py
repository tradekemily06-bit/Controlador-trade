from __future__ import annotations

from dataclasses import dataclass, field

from core.learning_content import LearningActivity, LearningAttempt, LearningObservation, LearningResource
from core.p128_learning_source_gate import LearningSource


@dataclass
class LearningScope:
    """All user-owned learning state for exactly one tenant+subject pair."""

    sources: dict[str, LearningSource] = field(default_factory=dict)
    resources: dict[str, LearningResource] = field(default_factory=dict)
    observations: list[LearningObservation] = field(default_factory=list)
    activities: dict[str, LearningActivity] = field(default_factory=dict)
    attempts: list[LearningAttempt] = field(default_factory=list)


class ScopedLearningState:
    """Separates learning state by trusted tenant+subject.

    This is an isolation layer, not the final durable SaaS data plane. Public
    SaaS remains fail-closed until a durable shared provider is configured.
    """

    def __init__(self) -> None:
        self._scopes: dict[tuple[str, str], LearningScope] = {}

    @staticmethod
    def _scope(tenant_id: str | None, subject_id: str | None) -> tuple[str, str] | None:
        if tenant_id is None and subject_id is None:
            return None
        tenant = str(tenant_id or "").strip()
        subject = str(subject_id or "").strip()
        if not tenant or not subject:
            raise PermissionError("tenant_id and subject_id are required for scoped learning state")
        return tenant, subject

    def get(self, *, tenant_id: str | None, subject_id: str | None) -> LearningScope | None:
        scope = self._scope(tenant_id, subject_id)
        if scope is None:
            return None
        return self._scopes.setdefault(scope, LearningScope())
