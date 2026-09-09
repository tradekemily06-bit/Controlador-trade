from __future__ import annotations

from dataclasses import dataclass

from core.p59_knowledge_lab import KnowledgeLabRun


@dataclass(frozen=True)
class AdaptationProposal:
    proposal_id: str
    lab_id: str
    memory_id: str
    hypothesis_id: str
    rationale: str
    applied: bool = False
    real_execution_allowed: bool = False


class AdaptationProposalBoundary:
    def propose(self, run: KnowledgeLabRun | None, *, proposal_id: str, rationale: str) -> AdaptationProposal:
        if not isinstance(run, KnowledgeLabRun):
            raise ValueError("invalid laboratory run")
        if not isinstance(proposal_id, str) or not proposal_id.strip():
            raise ValueError("proposal_id is required")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale is required")
        return AdaptationProposal(
            proposal_id=proposal_id.strip(),
            lab_id=run.lab_id,
            memory_id=run.memory_id,
            hypothesis_id=run.hypothesis_id,
            rationale=rationale.strip(),
        )
