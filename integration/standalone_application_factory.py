"""Wire existing read-only services to the one shared intelligence instance.

All identities and fiscal owner keys are injected by trusted server setup.
They are never accepted from an area request. Missing dependencies remain
NOT_CONNECTED rather than being replaced by demo data.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Mapping

from assistant.chat_service import EcosystemAssistant
from core.senior_context_orchestrator import SeniorContextInput
from core.unified_intelligence import ApplicationArea, UnifiedIntelligence
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from integration.unified_ecosystem_application import UnifiedEcosystemApplication


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def build_standalone_application(
    *,
    ecosystem_service: Any,
    fiscal_reserve: FiscalReserve | None = None,
    fiscal_owner_id: str | None = None,
    foreign_pending: FiscalPendingQueue | None = None,
    domestic_pending: FiscalDomesticPendingQueue | None = None,
    assistant: EcosystemAssistant | None = None,
    trusted_identity: str | None = None,
    intelligence: UnifiedIntelligence | None = None,
    market_analyzer: Any | None = None,
    market_data_registry: Any | None = None,
) -> UnifiedEcosystemApplication:
    """Compose the seven areas around one shared intelligence coordinator.

    This factory is read-only with respect to trading and fiscal records.
    Fiscal write workflows require separate authenticated application actions.
    """
    if ecosystem_service is None:
        raise ValueError("ecosystem_service is required")
    if fiscal_reserve is not None and (
        not isinstance(fiscal_owner_id, str) or not fiscal_owner_id.strip()
    ):
        raise ValueError("fiscal_owner_id must come from trusted server configuration")

    senior_context = getattr(ecosystem_service, "senior_context", None)
    intelligence = intelligence or (UnifiedIntelligence(senior_context=senior_context) if senior_context is not None else UnifiedIntelligence())
    app = UnifiedEcosystemApplication(intelligence=intelligence)
    app.market_data_provider_status = "REGISTERED_NOT_TESTED" if market_analyzer is not None else "NOT_CONFIGURED"
    app.market_data_registry = market_data_registry

    def command_cabin(task: str, context: Mapping[str, Any], shared: UnifiedIntelligence):
        return _plain({
            "system": ecosystem_service.system_status(),
            "risk": ecosystem_service.risk_status(),
            "operations": ecosystem_service.operational_observability(),
            "notifications": (
                ecosystem_service.notification_summary()
                if callable(getattr(ecosystem_service, "notification_summary", None))
                else {"status": "NOT_CONFIGURED"}
            ),
            "notification_items": (
                ecosystem_service.notification_items(include_info=True)
                if callable(getattr(ecosystem_service, "notification_items", None))
                else []
            ),
            "health_alerts": (
                ecosystem_service.health_alerts()
                if callable(getattr(ecosystem_service, "health_alerts", None))
                else []
            ),
            "execution_authorized": False,
        })

    def analysis(task: str, context: Mapping[str, Any], shared: UnifiedIntelligence):
        operation = str(context.get("operation", "overview")).strip().lower()
        if operation in {"statistics", "performance"}:
            return _plain({
                "statistics": ecosystem_service.statistics(),
                "reporting_status": "STATISTICS_AVAILABLE",
                "execution_authorized": False,
            })
        if operation in {"reports", "report", "export"}:
            report_builder = getattr(ecosystem_service, "decision_report", None)
            if not callable(report_builder):
                return {"status": "REPORT_NOT_CONNECTED", "execution_authorized": False}
            limit = context.get("limit", 1000)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
                raise ValueError("limit must be an integer from 1 to 1000")
            return _plain({
                "report": report_builder(limit=limit),
                "reporting_status": "DECISION_REPORT_READY",
                "execution_authorized": False,
            })
        if operation in {"news", "market_news"}:
            limit = context.get("limit", 10)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
                raise ValueError("limit must be an integer from 1 to 50")
            return _plain({
                "news": ecosystem_service.news_status(limit=limit, symbol=context.get("symbol")),
                "execution_authorized": False,
            })
        if market_analyzer is not None:
            symbol = context.get("symbol")
            timeframe = context.get("timeframe", "5m")
            limit = context.get("limit", 120)
            confirmed = context.get("confirmed", False)
            filters_ok = context.get("filters_ok", True)
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("symbol é obrigatório para análise")
            result = market_analyzer.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                confirmed=confirmed,
                filters_ok=filters_ok,
            )
            return _plain(result)
        request = context.get("senior_context_input")
        if isinstance(request, SeniorContextInput):
            assessment = shared.assess_market(request)
            return _plain({
                "assessment": assessment,
                "execution_authorized": False,
                "decision_authority": "NOT_GRANTED",
            })
        return {
            "status": "DATA_PROVIDER_NOT_CONFIGURED",
            "message": "A inteligência está pronta para receber provedores, mas nenhuma fonte de candles foi conectada a este runtime.",
            "execution_authorized": False,
        }

    def study(task: str, context: Mapping[str, Any], shared: UnifiedIntelligence):
        operation = str(context.get("operation", "overview")).strip().lower()
        learning = ecosystem_service.learning_summary()
        if operation in {"replay", "laboratory_replay"}:
            cases = context.get("cases")
            if not isinstance(cases, list) or not cases or len(cases) > 100:
                raise ValueError("cases deve ser uma lista com 1 a 100 cenários")
            replay = getattr(ecosystem_service, "replay", None)
            if not callable(replay):
                return {"status": "NOT_CONFIGURED", "execution_authorized": False}
            return _plain({
                "replay": replay(cases),
                "execution_authorized": False,
            })
        if operation in {"sources", "learning_sources"}:
            payload = {"learning_sources": ecosystem_service.learning_sources_view()}
        elif operation in {"resources", "learning_resources"}:
            payload = {"resources": ecosystem_service.learning_resources_view()}
        elif operation in {"observations", "learning_observations"}:
            payload = {"observations": ecosystem_service.learning_observations_view()}
        elif operation in {"activities", "learning_activities"}:
            payload = {
                "activities": ecosystem_service.learning_activities_view(),
                "professor_uses_validated_knowledge_only": True,
            }
        elif operation in {"attempts", "learning_attempts"}:
            payload = {
                "attempts": learning.get("attempts", []),
                "professor_uses_validated_knowledge_only": True,
            }
        else:
            payload = {"learning": learning, "statistics": ecosystem_service.statistics()}
        return _plain({
            **payload,
            "curriculum": [
                {
                    "module_id": module.module_id,
                    "title": module.title,
                    "domain": module.domain.value,
                    "stage": module.stage.value,
                    "execution_authorized": False,
                }
                for module in shared.curriculum.modules
            ],
            "execution_authorized": False,
        })

    def memory(task: str, context: Mapping[str, Any], shared: UnifiedIntelligence):
        limit = context.get("limit", 50)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        operation = str(context.get("operation", "overview")).strip().lower()
        if operation in {"report", "reports", "export"}:
            report_builder = getattr(ecosystem_service, "decision_report", None)
            if not callable(report_builder):
                return {"status": "REPORT_NOT_CONNECTED", "execution_authorized": False}
            return _plain({
                "report": report_builder(limit=min(limit, 1000)),
                "execution_authorized": False,
            })
        return _plain({
            "records": ecosystem_service.memory_view(limit=limit),
            "statistics": ecosystem_service.statistics(),
            "execution_authorized": False,
        })

    def fiscal(task: str, context: Mapping[str, Any], shared: UnifiedIntelligence):
        if fiscal_reserve is None or not fiscal_owner_id:
            return {"status": "NOT_CONFIGURED", "execution_authorized": False}
        return _plain({
            "reserve": fiscal_reserve.summary(fiscal_owner_id),
            "foreign_pending": (
                foreign_pending.summary(fiscal_owner_id)
                if foreign_pending is not None else {"status": "NOT_CONFIGURED"}
            ),
            "domestic_pending": (
                domestic_pending.summary(fiscal_owner_id)
                if domestic_pending is not None else {"status": "NOT_CONFIGURED"}
            ),
            "tax_calculation_authorized": False,
            "execution_authorized": False,
        })

    def ecosystem_assistant(task: str, context: Mapping[str, Any], shared: UnifiedIntelligence):
        if assistant is None:
            return {"status": "NOT_CONFIGURED", "execution_authorized": False}
        if not trusted_identity or not fiscal_owner_id:
            return {"status": "TRUSTED_IDENTITY_NOT_CONFIGURED", "execution_authorized": False}
        intelligence_route = shared.route(
            area=ApplicationArea.ECOSYSTEM_ASSISTANT, task=task
        )
        architecture = shared.architecture_status()
        result = assistant.ask(
            identity=trusted_identity,
            message=task,
            fiscal_owner_id=fiscal_owner_id,
            cid=context.get("conversation_id"),
            shared_intelligence_context={
                "architecture": architecture["architecture"],
                "area": intelligence_route.area.value,
                "selected_capabilities": list(intelligence_route.selected_capabilities),
                "shared_capabilities": architecture["shared_capabilities"],
                "internal_knowledge": architecture["internal_knowledge"],
            },
        )
        return _plain({**result, "execution_authorized": False})

    def control_center(task: str, context: Mapping[str, Any], shared: UnifiedIntelligence):
        return _plain({
            "connections": ecosystem_service.connections(),
            "saas": ecosystem_service.saas_status(),
            "preferences": (
                ecosystem_service.get_preferences()
                if callable(getattr(ecosystem_service, "get_preferences", None))
                else {"status": "NOT_CONFIGURED"}
            ),
            "market_data_providers": (
                market_data_registry.status()
                if market_data_registry is not None else {"status": "NOT_CONFIGURED", "count": 0}
            ),
            "execution_authorized": False,
        })

    app.register_handler(ApplicationArea.COMMAND_CABIN, command_cabin)
    app.register_handler(ApplicationArea.ANALYSIS, analysis)
    app.register_handler(ApplicationArea.STUDY, study)
    app.register_handler(ApplicationArea.MEMORY, memory)
    if fiscal_reserve is not None:
        app.register_handler(ApplicationArea.TAX_RESERVE, fiscal)
    if assistant is not None:
        app.register_handler(ApplicationArea.ECOSYSTEM_ASSISTANT, ecosystem_assistant)
    app.register_handler(ApplicationArea.CONTROL_CENTER, control_center)
    return app
