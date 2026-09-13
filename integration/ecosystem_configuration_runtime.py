from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity, UpdateKind
from core.ecosystem_preferences import ChartTheme, EcosystemPreferencesStore
from integration.ecosystem_service import EcosystemService


class ConfiguredEcosystemService(EcosystemService):
    """Ecosystem service with preferences and material notifications wired in.

    Preferences remain configuration-only and cannot grant autonomy or REAL
    execution. Notifications are observability only and never authorize trades.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.preferences = EcosystemPreferencesStore()
        self.notifications = EcosystemNotificationCenter()

    def get_preferences(self) -> dict[str, Any]:
        value = self.preferences.preferences
        result = asdict(value)
        result["chart_theme"] = value.chart_theme.value
        result["candle"]["style"] = value.candle.style.value
        result["candle"]["color_mode"] = value.candle.color_mode.value
        return result

    def update_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        changes = dict(payload)
        if "chart_theme" in changes and isinstance(changes["chart_theme"], str):
            changes["chart_theme"] = ChartTheme(changes["chart_theme"].upper())
        self.preferences.update(**changes)
        return self.get_preferences()

    def update_candle_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        changes = dict(payload)
        from core.ecosystem_preferences import CandleColorMode, CandleStyle
        if "style" in changes and isinstance(changes["style"], str):
            changes["style"] = CandleStyle(changes["style"].upper())
        if "color_mode" in changes and isinstance(changes["color_mode"], str):
            changes["color_mode"] = CandleColorMode(changes["color_mode"].upper())
        self.preferences.update_candle(**changes)
        return self.get_preferences()

    def update_notification_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.preferences.update_notifications(**dict(payload))
        return self.get_preferences()

    def _notification_visible(self, item: EcosystemNotification) -> bool:
        prefs = self.preferences.preferences.notifications
        if item.severity is NotificationSeverity.CRITICAL:
            return True
        if item.severity is NotificationSeverity.INFO:
            return prefs.info_enabled
        if not prefs.important_enabled:
            return False
        category_enabled = {
            NotificationKind.SYSTEM_UPDATE: prefs.system_updates_enabled,
            NotificationKind.SECURITY: prefs.security_enabled,
            NotificationKind.MARKET: prefs.market_enabled,
            NotificationKind.RISK: prefs.risk_enabled,
            NotificationKind.CONNECTION: prefs.connection_enabled,
            NotificationKind.EXECUTION: prefs.execution_enabled,
            NotificationKind.LEARNING: prefs.learning_enabled,
            NotificationKind.RECOVERY: prefs.recovery_enabled,
        }[item.kind]
        return category_enabled

    def _visible_notifications(self, *, include_info: bool = False) -> tuple[EcosystemNotification, ...]:
        events = self.notifications.visible(include_info=include_info)
        return tuple(item for item in events if self._notification_visible(item))

    def notification_summary(self) -> dict[str, Any]:
        visible = self._visible_notifications(include_info=False)
        return {
            "count": len(visible),
            "critical_count": len(self.notifications.critical()),
            "items": [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in visible],
        }

    def all_notifications(self) -> list[dict[str, Any]]:
        return [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in self.notifications.all()]

    def publish_ecosystem_update(self, title: str, message: str, *, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> dict[str, Any]:
        notification_id = f"update-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish_update(notification_id, title, message, important=True, update_kind=update_kind)
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def publish_material_event(self, kind: str, title: str, message: str, *, critical: bool = False, blocking: bool = False) -> dict[str, Any]:
        """Route a material runtime event into the notification center."""
        notification_kind = NotificationKind(str(kind).upper())
        severity = NotificationSeverity.CRITICAL if critical else NotificationSeverity.IMPORTANT
        notification_id = f"event-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish(EcosystemNotification(notification_id, notification_kind, severity, title, message, requires_attention=critical or blocking, blocking=blocking))
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}
