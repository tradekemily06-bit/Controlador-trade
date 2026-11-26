"""Application facade exposing one intelligence to all seven areas.

This facade is read-only by default. Area-specific handlers may be attached as
integration work is completed. An unregistered handler is reported as
NOT_CONNECTED rather than simulated or silently treated as ready.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from core.unified_intelligence import ApplicationArea, UnifiedIntelligence


AreaHandler = Callable[[str, Mapping[str, Any], UnifiedIntelligence], Mapping[str, Any]]


class UnifiedEcosystemApplication:
    def __init__(
        self,
        *,
        intelligence: UnifiedIntelligence | None = None,
        handlers: Mapping[ApplicationArea, AreaHandler] | None = None,
    ) -> None:
        self.intelligence = intelligence or UnifiedIntelligence()
        self._handlers: dict[ApplicationArea, AreaHandler] = dict(handlers or {})

    def register_handler(self, area: ApplicationArea, handler: AreaHandler) -> None:
        if not isinstance(area, ApplicationArea):
            raise ValueError("area must be an ApplicationArea")
        if not callable(handler):
            raise ValueError("handler must be callable")
        if area in self._handlers:
            raise ValueError("an area handler is already registered")
        self._handlers[area] = handler

    def architecture(self) -> dict[str, Any]:
        status = self.intelligence.architecture_status()
        status["area_handler_status"] = {
            area.value: ("CONNECTED" if area in self._handlers else "NOT_CONNECTED")
            for area in ApplicationArea
        }
        status["all_area_handlers_connected"] = len(self._handlers) == len(ApplicationArea)
        status["market_data_provider_status"] = getattr(self, "market_data_provider_status", "NOT_CONFIGURED")
        registry = getattr(self, "market_data_registry", None)
        status["market_data_providers"] = registry.status() if registry is not None else {"status": "NOT_CONFIGURED", "count": 0}
        return status

    def handle(
        self,
        *,
        area: ApplicationArea | str,
        task: str,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        route = self.intelligence.route(area=area, task=task)
        handler = self._handlers.get(route.area)
        if handler is None:
            return {
                "request_id": route.request_id,
                "area": route.area.value,
                "area_name": route.area_contract.name,
                "status": "NOT_CONNECTED",
                "route": list(route.selected_capabilities),
                "execution_authorized": False,
                "message": "A área está mapeada para a inteligência central, mas seu serviço funcional ainda não foi conectado.",
            }
        result = handler(route.task, dict(context or {}), self.intelligence)
        if not isinstance(result, Mapping):
            raise ValueError("area handler must return a mapping")
        if result.get("execution_authorized") is True or result.get("order_submitted") is True:
            raise ValueError("standalone analyst application handlers cannot authorize or submit orders")
        return {
            "request_id": route.request_id,
            "area": route.area.value,
            "area_name": route.area_contract.name,
            "status": "CONNECTED",
            "result": dict(result),
            "execution_authorized": False,
        }
