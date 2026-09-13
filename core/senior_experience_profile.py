"""Persistent professional baseline for the ecosystem's senior market role.

The profile is an architectural capability contract, not a claim that a human
employee exists. The ecosystem starts with a 45+ professional baseline;
being newly connected to a user is represented separately as onboarding state
and never resets or reduces accumulated experience. There is deliberately no
upper experience ceiling: validated knowledge, research and capability can
continue to grow without being constrained by the initial baseline number.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExperienceScope(str, Enum):
    MARKET_KNOWLEDGE = "MARKET_KNOWLEDGE"
    CONTEXTUAL_REASONING = "CONTEXTUAL_REASONING"
    RISK = "RISK"
    EXECUTION = "EXECUTION"
    RESEARCH = "RESEARCH"
    AUDIT = "AUDIT"
    TEACHING = "TEACHING"
    SECURITY = "SECURITY"


@dataclass(frozen=True)
class SeniorExperienceProfile:
    """Professional baseline available from the first operational day."""

    experience_years: int = 45
    newly_assigned_to_user: bool = True
    experience_resets_on_assignment: bool = False
    scopes: tuple[ExperienceScope, ...] = tuple(ExperienceScope)

    def validate(self) -> None:
        if self.experience_years < 45:
            raise ValueError("the senior ecosystem baseline must preserve at least 45 years")
        if not self.scopes:
            raise ValueError("senior experience scopes are required")
        if self.experience_resets_on_assignment:
            raise ValueError("assignment must never reset senior experience")

    @property
    def first_day_with_user(self) -> bool:
        """True only for relationship/onboarding state, never experience state."""
        return self.newly_assigned_to_user

    @property
    def is_45_plus(self) -> bool:
        """Expose the baseline as an open-ended 45+ capability, not a ceiling."""
        self.validate()
        return self.experience_years >= 45

    def professional_posture(self) -> tuple[str, ...]:
        self.validate()
        return (
            "Use accumulated market knowledge before forming a conclusion.",
            "Compare history, present state, relationships, evidence and counterevidence.",
            "Treat uncertainty and missing context as information, not as permission to guess.",
            "Reassess when assumptions conflict with observed evidence.",
            "Separate professional judgment from authorization to execute.",
            "Keep researching and updating knowledge without silently changing operational rules.",
            "Continue capability growth without an artificial upper experience limit.",
        )
