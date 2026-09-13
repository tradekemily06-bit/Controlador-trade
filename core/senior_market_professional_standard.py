"""Cross-domain standard for senior-level financial-market capabilities.

This is a quality contract, not a collection of trading rules. A capability is
considered senior only when it can reason with context, uncertainty,
contradictory evidence, exceptions, provenance, risk and post-result review.
Learning or knowledge depth never grants execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SeniorDimension(str, Enum):
    KNOWLEDGE = "knowledge"
    CONTEXT = "context"
    REASONING = "reasoning"
    EVIDENCE = "evidence"
    UNCERTAINTY = "uncertainty"
    RISK = "risk"
    EXECUTION = "execution"
    AUDIT = "audit"
    LEARNING = "learning"
    SECURITY = "security"


@dataclass(frozen=True)
class SeniorCapabilityStandard:
    """Minimum quality contract shared by every ecosystem capability."""

    capability_id: str
    domains: tuple[str, ...]
    dimensions: tuple[SeniorDimension, ...]
    handles_conflicts: bool = True
    handles_exceptions: bool = True
    requires_provenance: bool = True
    requires_reassessment: bool = True
    execution_authorized: bool = False

    def validate(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("capability_id is required")
        if not self.domains:
            raise ValueError("at least one domain is required")
        required = set(SeniorDimension)
        missing = required.difference(self.dimensions)
        if missing:
            raise ValueError(
                "senior standard is incomplete: "
                + ", ".join(sorted(item.value for item in missing))
            )
        if not self.handles_conflicts or not self.handles_exceptions:
            raise ValueError("senior capability must handle conflicts and exceptions")
        if not self.requires_provenance or not self.requires_reassessment:
            raise ValueError("senior capability requires provenance and reassessment")
        if self.execution_authorized:
            raise ValueError("quality standard cannot grant execution authority")


SENIOR_FINANCIAL_MARKET_STANDARD = SeniorCapabilityStandard(
    capability_id="SENIOR-FINANCIAL-MARKET-END-TO-END",
    domains=(
        "financial_education",
        "markets",
        "investments",
        "trading",
        "risk",
        "macro",
        "fundamental_analysis",
        "technical_analysis",
        "quantitative_analysis",
        "portfolio_management",
        "execution",
        "automation",
        "regulation_ethics",
        "research",
    ),
    dimensions=tuple(SeniorDimension),
)


def assert_senior_standard() -> SeniorCapabilityStandard:
    """Validate and return the canonical standard for composition by services."""
    SENIOR_FINANCIAL_MARKET_STANDARD.validate()
    return SENIOR_FINANCIAL_MARKET_STANDARD
