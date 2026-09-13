"""Persistent 45+ professional baseline for the ecosystem's senior market role.

The profile is an architectural capability contract, not a claim that a human
employee exists. The ecosystem starts with a 45+ professional baseline;
being newly connected to a user is represented separately as onboarding state
and never resets, caps, or reduces accumulated experience.

The number 45 is a minimum baseline, not a ceiling. The profile deliberately
has no maximum experience value so validated research, learning and continued
professional development can extend the capability without creating an
artificial upper bound.
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
    """Professional baseline available from the first operational day.

    ``experience_years`` represents a minimum professional baseline contract,
    not a hard maximum. Values above 45 are valid by design.
    """

    experience_years: int = 45
    newly_assigned_to_user: bool = True
    experience_resets_on_assignment: bool = False
    experience_growth_enabled: bool = True
    experience_ceiling: int | None = None
    scopes: tuple[ExperienceScope, ...] = tuple(ExperienceScope)

    @property
    def minimum_experience_years(self) -> int:
        return 45

    @property
    def is_45_plus(self) -> bool:
        return self.experience_years >= self.minimum_experience_years

    def validate(self) -> None:
        if not isinstance(self.experience_years, int) or isinstance(self.experience_years, bool):
            raise ValueError("experience_years must be an integer")
        if self.experience_years < self.minimum_experience_years:
            raise ValueError("the senior ecosystem baseline must preserve at least 45 years")
        if not self.scopes:
            raise ValueError("senior experience scopes are required")
        if self.experience_resets_on_assignment:
            raise ValueError("assignment must never reset senior experience")
        if not self.experience_growth_enabled:
            raise ValueError("senior experience must remain open to continued development")
        if self.experience_ceiling is not None:
            raise ValueError("senior experience must not have an artificial ceiling")

    @property
    def first_day_with_user(self) -> bool:
        """True only for relationship/onboarding state, never experience state."""
        return self.newly_assigned_to_user

    def professional_posture(self) -> tuple[str, ...]:
        self.validate()
        return (
            "Use accumulated market knowledge before forming a conclusion.",
            "Treat 45+ years as a minimum professional baseline, never as a ceiling.",
            "Continue developing knowledge and professional capability without an artificial upper bound.",
            "Compare history, present state, relationships, evidence and counterevidence.",
            "Treat uncertainty and missing context as information, not as permission to guess.",
            "Reassess when assumptions conflict with observed evidence.",
            "Separate professional judgment from authorization to execute.",
            "Keep researching and updating knowledge without silently changing operational rules.",
        )
