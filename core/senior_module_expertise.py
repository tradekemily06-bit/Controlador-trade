"""Senior capability bridge for current and future ecosystem modules."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .financial_market_curriculum import CurriculumModule, SeniorFinancialMarketCurriculum
from .senior_experience_profile import SeniorExperienceProfile

class ModuleExpertiseStatus(str, Enum):
    CAPABILITY_READY = "CAPABILITY_READY"
    REQUIRES_DOMAIN_VALIDATION = "REQUIRES_DOMAIN_VALIDATION"

@dataclass(frozen=True)
class SeniorModuleExpertise:
    module_id: str
    domain: str
    experience_years: int
    status: ModuleExpertiseStatus
    advanced_capabilities: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    execution_authorized: bool = False
    experience_is_open_ended: bool = True
    def validate(self) -> None:
        if not self.module_id.strip() or not self.domain.strip(): raise ValueError("module identity is required")
        if self.experience_years < 45: raise ValueError("module expertise must preserve the 45+ baseline")
        if not self.experience_is_open_ended: raise ValueError("module expertise cannot have an upper experience ceiling")
        if not self.advanced_capabilities: raise ValueError("advanced capabilities are required")
        if not self.evidence_requirements: raise ValueError("evidence requirements are required")
        if self.execution_authorized: raise ValueError("module expertise cannot authorize execution")

class SeniorModuleExpertiseRegistry:
    def __init__(self, profile: SeniorExperienceProfile | None = None):
        self.profile = profile or SeniorExperienceProfile(); self.profile.validate(); self._known: dict[str, SeniorModuleExpertise] = {}
    def resolve(self, module: CurriculumModule) -> SeniorModuleExpertise:
        if not isinstance(module, CurriculumModule): raise ValueError("module must be a CurriculumModule")
        cached = self._known.get(module.module_id)
        if cached and cached.experience_years >= self.profile.experience_years: return cached
        expertise = SeniorModuleExpertise(module_id=module.module_id, domain=module.domain.value, experience_years=self.profile.experience_years, status=ModuleExpertiseStatus.CAPABILITY_READY, advanced_capabilities=tuple(dict.fromkeys((*module.senior_capabilities, *module.practical_competencies, *module.topics))), evidence_requirements=("Current authoritative sources appropriate to the module.", "Historical context and regime changes relevant to the module.", "Independent evidence and explicit counterevidence.", "Validation and test provenance before operational reuse.", "Current data-quality and jurisdiction/session context when applicable."))
        expertise.validate(); self._known[module.module_id] = expertise; return expertise
    def resolve_all(self, curriculum: SeniorFinancialMarketCurriculum | None = None) -> tuple[SeniorModuleExpertise, ...]:
        curriculum = curriculum or SeniorFinancialMarketCurriculum(); return tuple(self.resolve(module) for module in curriculum.modules)
    def register_future_module(self, module: CurriculumModule) -> SeniorModuleExpertise:
        expertise = self.resolve(module)
        return SeniorModuleExpertise(module_id=expertise.module_id, domain=expertise.domain, experience_years=expertise.experience_years, status=ModuleExpertiseStatus.REQUIRES_DOMAIN_VALIDATION, advanced_capabilities=expertise.advanced_capabilities, evidence_requirements=expertise.evidence_requirements)
    @property
    def module_count(self) -> int: return len(self._known)
    def all_registered(self) -> tuple[SeniorModuleExpertise, ...]: return tuple(self._known.values())
