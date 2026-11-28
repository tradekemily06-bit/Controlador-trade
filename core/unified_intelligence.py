"""One shared intelligence core for the six visible application areas.

This is an integration/orchestration layer over verified ecosystem capabilities.
It is not a claim of AGI/ASI and it does not provide execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from core.financial_market_curriculum import SeniorFinancialMarketCurriculum
from core.senior_domain_expertise import SeniorDomainExpertiseRegistry
from core.senior_experience_profile import SeniorExperienceProfile
from core.senior_context_orchestrator import SeniorContextInput, SeniorContextOrchestrator
from core.senior_module_expertise import SeniorModuleExpertiseRegistry


class ApplicationArea(str, Enum):
    """Visible routes plus the legacy internal memory capability."""

    COMMAND_CABIN = "command_cabin"
    ANALYSIS = "analysis"
    STUDY = "study"
    MEMORY = "memory"
    TAX_RESERVE = "tax_reserve"
    ECOSYSTEM_ASSISTANT = "ecosystem_assistant"
    CONTROL_CENTER = "control_center"


VISIBLE_APPLICATION_AREAS = (
    ApplicationArea.COMMAND_CABIN,
    ApplicationArea.ANALYSIS,
    ApplicationArea.STUDY,
    ApplicationArea.TAX_RESERVE,
    ApplicationArea.ECOSYSTEM_ASSISTANT,
    ApplicationArea.CONTROL_CENTER,
)


@dataclass(frozen=True)
class AreaContract:
    area: ApplicationArea
    name: str
    responsibilities: tuple[str, ...]
    capabilities: tuple[str, ...]
    permitted_actions: tuple[str, ...]
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.responsibilities or not self.capabilities:
            raise ValueError("area contracts require a name, responsibilities and capabilities")
        if self.execution_authorized:
            raise ValueError("application areas cannot grant execution authority")


@dataclass(frozen=True)
class IntelligenceRoute:
    request_id: str
    area: ApplicationArea
    task: str
    selected_capabilities: tuple[str, ...]
    area_contract: AreaContract
    status: str = "ROUTED"
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.task.strip():
            raise ValueError("request_id and task are required")
        if self.execution_authorized:
            raise ValueError("intelligence routing cannot authorize execution")


_AREA_CONTRACTS: Mapping[ApplicationArea, AreaContract] = {
    ApplicationArea.COMMAND_CABIN: AreaContract(
        ApplicationArea.COMMAND_CABIN,
        "Cabine de Comando",
        ("visão operacional", "decisões e qualidade", "estado e bloqueios de risco", "simulação", "notificações", "kill switch"),
        ("shared_intelligence", "market_analysis", "decision_quality", "risk", "notifications", "operational_safety"),
        ("read", "analyze", "simulate", "acknowledge_alert"),
    ),
    ApplicationArea.ANALYSIS: AreaContract(
        ApplicationArea.ANALYSIS,
        "Análise",
        ("análise de mercado", "estatísticas", "relatórios", "contexto e evidências"),
        ("shared_intelligence", "market_analysis", "statistics", "reporting", "research"),
        ("read", "analyze", "report"),
    ),
    ApplicationArea.STUDY: AreaContract(
        ApplicationArea.STUDY,
        "Estudo",
        ("laboratório", "replay", "simulador", "aprendizado", "descobertas", "escola", "tutorial", "onboarding"),
        ("shared_intelligence", "curriculum", "learning", "research", "validation", "simulation"),
        ("read", "study", "simulate", "submit_learning_evidence"),
    ),
    ApplicationArea.MEMORY: AreaContract(
        ApplicationArea.MEMORY,
        "Memória",
        ("histórico", "registros", "resultados", "contexto aprendido", "proveniência"),
        ("shared_intelligence", "memory", "audit", "validated_knowledge"),
        ("read", "record", "review", "export"),
    ),
    ApplicationArea.TAX_RESERVE: AreaContract(
        ApplicationArea.TAX_RESERVE,
        "Reserva Fiscal",
        ("filas Brasil e Exterior", "lançamentos", "pendências", "histórico", "revisão documental"),
        ("shared_intelligence", "financial_knowledge", "document_review", "audit"),
        ("read", "classify", "record", "review", "export"),
    ),
    ApplicationArea.ECOSYSTEM_ASSISTANT: AreaContract(
        ApplicationArea.ECOSYSTEM_ASSISTANT,
        "Assistente do Ecossistema",
        ("consulta e análise do ecossistema", "explicação de riscos", "consulta da Reserva Fiscal"),
        ("shared_intelligence", "cross_area_context", "risk", "financial_knowledge", "memory"),
        ("read", "analyze", "explain"),
    ),
    ApplicationArea.CONTROL_CENTER: AreaContract(
        ApplicationArea.CONTROL_CENTER,
        "Central",
        ("financeiro", "configurações", "auditoria", "segurança", "conexões", "Multi-Broker"),
        ("shared_intelligence", "configuration", "security", "audit", "connectivity", "broker_adapters"),
        ("read", "configure", "audit", "manage_connections"),
    ),
}


class UnifiedIntelligence:
    """One coordinator selecting internal capabilities for every area.

    Specialized components remain internal capabilities, not independent
    user-facing intelligences. Only capabilities present in code are reported.
    Live providers and unverified integrations remain explicitly unconfigured
    or pending validation.
    """

    def __init__(
        self,
        *,
        experience_profile: SeniorExperienceProfile | None = None,
        senior_context: SeniorContextOrchestrator | None = None,
    ) -> None:
        self.experience_profile = experience_profile or SeniorExperienceProfile()
        self.experience_profile.validate()
        self.domains = SeniorDomainExpertiseRegistry(self.experience_profile)
        self.curriculum = SeniorFinancialMarketCurriculum()
        self.module_expertise = SeniorModuleExpertiseRegistry(self.experience_profile)
        self.senior_context = senior_context or SeniorContextOrchestrator()

    @property
    def areas(self) -> tuple[AreaContract, ...]:
        return tuple(_AREA_CONTRACTS[area] for area in VISIBLE_APPLICATION_AREAS)

    def route(self, *, area: ApplicationArea | str, task: str) -> IntelligenceRoute:
        if isinstance(area, str):
            try:
                area = ApplicationArea(area.strip().lower())
            except ValueError as exc:
                raise ValueError("área do aplicativo desconhecida") from exc
        if not isinstance(area, ApplicationArea):
            raise ValueError("area must be an ApplicationArea")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task is required")
        contract = _AREA_CONTRACTS[area]
        return IntelligenceRoute(
            request_id=str(uuid4()),
            area=area,
            task=task.strip(),
            selected_capabilities=contract.capabilities,
            area_contract=contract,
        )

    def assess_market(self, request: SeniorContextInput):
        """Use the existing senior context pipeline without granting execution."""
        result = self.senior_context.assess(request)
        if result.execution_authorized:
            raise RuntimeError("senior context must never authorize execution")
        return result

    def architecture_status(self) -> dict[str, Any]:
        profile = self.experience_profile
        profile.validate()
        return {
            "architecture": "ONE_SHARED_INTELLIGENCE",
            "application_areas": [
                {
                    "id": contract.area.value,
                    "name": contract.name,
                    "responsibilities": list(contract.responsibilities),
                    "capabilities": list(contract.capabilities),
                    "permitted_actions": list(contract.permitted_actions),
                    "execution_authorized": False,
                }
                for contract in self.areas
            ],
            "internal_knowledge": {
                "senior_experience_baseline_years": profile.experience_years,
                "experience_open_ended": True,
                "specialist_domains": list(self.domains.current_domains()),
                "curriculum_modules": len(self.curriculum.modules),
                "curriculum_is_internal_knowledge": True,
                "module_expertise_is_internal": True,
            },
            "internal_capabilities": ["decision_memory", "audit_history", "validated_knowledge"],
            "visible_area_count": len(self.areas),
            "shared_capabilities": [
                "contextual_reasoning",
                "evidence_and_counterevidence",
                "risk_assessment",
                "memory_and_validated_knowledge",
                "research_and_learning",
                "audit_and_security",
                "cross_area_context",
            ],
            "limitations": {
                "agi_or_asi_claimed": False,
                "external_foundation_model": "NOT_CONFIGURED_BY_THIS_LAYER",
                "live_market_provider": "MUST_BE_VALIDATED_PER_ADAPTER",
                "external_push_notifications": "MUST_BE_CONFIGURED_AND_TESTED",
            },
            "execution_authorized": False,
        }
