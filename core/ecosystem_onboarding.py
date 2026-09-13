"""Guided first-use mode for learning where the ecosystem's capabilities live.

This is an educational/navigation layer only. It never grants trading, execution,
risk override, autonomy, or security authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OnboardingSection(str, Enum):
    OPERATION = "OPERATION"
    ANALYSIS = "ANALYSIS"
    LEARNING = "LEARNING"
    MEMORY = "MEMORY"
    RISK = "RISK"
    SECURITY = "SECURITY"
    HISTORY = "HISTORY"
    CONNECTIONS = "CONNECTIONS"
    SETTINGS = "SETTINGS"
    HELP = "HELP"


@dataclass(frozen=True)
class OnboardingStep:
    step_id: str
    title: str
    purpose: str
    location: OnboardingSection
    action_hint: str
    technical_details_hidden: bool = True


@dataclass(frozen=True)
class OnboardingGuide:
    guide_id: str
    title: str
    steps: tuple[OnboardingStep, ...]
    completion_message: str
    execution_authorized: bool = False


class EcosystemOnboarding:
    """Provides a concise, contextual tour without exposing technical clutter."""

    def build_first_use_guide(self) -> OnboardingGuide:
        steps = (
            OnboardingStep("operation", "Operação", "Ver o estado atual e as decisões relevantes sem poluir a tela.", OnboardingSection.OPERATION, "Comece aqui para acompanhar o mercado."),
            OnboardingStep("analysis", "Análise", "Entender por que o ecossistema está lendo o mercado daquela forma.", OnboardingSection.ANALYSIS, "Abra quando quiser investigar a leitura."),
            OnboardingStep("risk", "Risco", "Ver os riscos materiais antes de qualquer operação.", OnboardingSection.RISK, "Consulte quando houver decisão ou alerta de risco."),
            OnboardingStep("learning", "Ensino", "Aprender conceitos, processos e como usar cada recurso.", OnboardingSection.LEARNING, "Use para estudar ou aprender uma função."),
            OnboardingStep("memory", "Memória", "Consultar o que foi aprendido, validado e auditado.", OnboardingSection.MEMORY, "Use para acompanhar conhecimento e histórico de aprendizado."),
            OnboardingStep("history", "Histórico", "Revisar operações, decisões, resultados e auditorias.", OnboardingSection.HISTORY, "Use depois de uma operação ou para revisão."),
            OnboardingStep("connections", "Conexões", "Acompanhar fontes, mercado e integrações disponíveis.", OnboardingSection.CONNECTIONS, "Abra quando precisar verificar uma conexão."),
            OnboardingStep("security", "Segurança", "Entender bloqueios, proteção e estados críticos.", OnboardingSection.SECURITY, "Consulte quando houver alerta de segurança."),
            OnboardingStep("settings", "Configurações", "Ajustar preferências sem alterar as regras de segurança.", OnboardingSection.SETTINGS, "Use somente quando precisar personalizar o ambiente."),
            OnboardingStep("help", "Ajuda", "Encontrar explicações e orientação contextual.", OnboardingSection.HELP, "Use a ajuda contextual em qualquer tela."),
        )
        return OnboardingGuide(
            guide_id="first-use",
            title="Primeiros passos no ecossistema",
            steps=steps,
            completion_message="Você já sabe onde encontrar as funções principais. O ensino contextual continua disponível quando precisar.",
            execution_authorized=False,
        )
