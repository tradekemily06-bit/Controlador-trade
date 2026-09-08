from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from execution.paper import PaperExecution


@dataclass(frozen=True)
class ReconciliationResult:
    total: int
    accepted: int
    rejected: int
    consistent: bool


class Reconciler:
    """Confere a consistência básica das execuções registradas."""

    def reconcile(
        self,
        executions: Iterable[PaperExecution],
    ) -> ReconciliationResult:
        items = tuple(executions)

        accepted = sum(item.result.accepted for item in items)
        rejected = len(items) - accepted

        ids = [
            item.result.external_id
            for item in items
            if item.result.accepted
        ]

        consistent = (
            accepted + rejected == len(items)
            and len(ids) == len(set(ids))
            and all(execution.result.external_id for execution in items if execution.result.accepted)
        )

        return ReconciliationResult(
            total=len(items),
            accepted=accepted,
            rejected=rejected,
            consistent=consistent,
        )
