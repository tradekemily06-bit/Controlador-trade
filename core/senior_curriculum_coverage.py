"""Formal coverage registry for the senior professional curriculum.

This registry closes an architectural gap: financial management is not merely
an isolated helper; it is explicitly part of the senior curriculum contract.
All listed capabilities remain non-execution knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass

from .senior_financial_management_depth import build_financial_management_depth
from .senior_professional_depth import build_senior_professional_depth


@dataclass(frozen=True)
class SeniorCurriculumCoverage:
    domains: tuple[str, ...]
    experience_years: int
    experience_is_open_ended: bool
    execution_authorized: bool


def build_senior_curriculum_coverage() -> SeniorCurriculumCoverage:
    advanced = build_senior_professional_depth()
    financial = build_financial_management_depth()
    domains = tuple(item.domain_id for item in advanced) + (financial.domain_id,)
    experience_years = min(
        [item.experience_years for item in advanced] + [financial.experience_years]
    )
    open_ended = all(
        [item.experience_is_open_ended for item in advanced]
        + [financial.experience_is_open_ended]
    )
    execution_authorized = any(
        [item.execution_authorized for item in advanced]
        + [financial.execution_authorized]
    )
    return SeniorCurriculumCoverage(
        domains=domains,
        experience_years=experience_years,
        experience_is_open_ended=open_ended,
        execution_authorized=execution_authorized,
    )
