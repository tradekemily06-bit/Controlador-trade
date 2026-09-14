from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass
class LearningScopeBucket(Generic[T]):
    """In-process scoped bucket used as a safety boundary before durable SaaS storage."""

    values: T


class ScopedLearningState:
    """Separates learning state by trusted tenant+subject without changing local mode.

    This is deliberately an isolation layer, not the final durable SaaS data plane.
    Public SaaS remains fail-closed until a durable shared provider is configured.
    """

    def __init__(self, factory):
        self._factory = factory
        self._scopes: dict[tuple[str, str], LearningScopeBucket] = {}

    @staticmethod
    def _scope(tenant_id: str | None, subject_id: str | None) -> tuple[str, str] | None:
        if tenant_id is None and subject_id is None:
            return None
        tenant = str(tenant_id or "").strip()
        subject = str(subject_id or "").strip()
        if not tenant or not subject:
            raise PermissionError("tenant_id and subject_id are required for scoped learning state")
        return tenant, subject

    def get(self, *, tenant_id: str | None, subject_id: str | None):
        scope = self._scope(tenant_id, subject_id)
        if scope is None:
            return None
        bucket = self._scopes.get(scope)
        if bucket is None:
            bucket = LearningScopeBucket(self._factory())
            self._scopes[scope] = bucket
        return bucket.values
