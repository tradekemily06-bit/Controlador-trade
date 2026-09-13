from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.ecosystem_notifications import EcosystemNotificationCenter, UpdateKind
from core.ecosystem_preferences import EcosystemPreferencesStore
from integration.ecosystem_service import EcosystemService


class ConfiguredEcosystemService(EcosystemService):
    """Ecosystem service with user preferences and material notifications wired in.

    Preferences stay presentation/configuration-only: they cannot enable autonomy
    or REAL execution. Notifications are informational/operational observability
    and never participate in trading authorization.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.preferences = EcosystemPreferencesStore()
        self.notifications = EcosystemNotificationCenter()

    def get_preferences(self) -> dict[str, Any]:
        value = self.preferences.preferences
        result = asdict(value)
        result["chart_theme"] = value.chart_theme.value
        result["candle_appearance"]["style"] = value.candle_appearance.style.value
        result["candle_appearance"]["color_mode"] = value.candle_appearance.color_mode.value
        return result

    def update_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.preferences.update(**payload)
        return self.get_preferences()

    def update_candle_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.preferences.update_candle(**payload)
        return self.get_preferences()

    def update_notification_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.preferences.update_notifications(**payload)
        return self.get_preferences()

    def notification_summary(self) -> dict[str, Any]:
        visible = self.notifications.visible(include_info=False)
        return {
            "count": len(visible),
            "critical_count": len(self.notifications.critical()),
            "items": [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in visible],
        }

    def all_notifications(self) -> list[dict[str, Any]]:
        return [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in self.notifications.all()]

    def publish_ecosystem_update(self, title: str, message: str, *, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> dict[str, Any]:
        item = self.notifications.publish_ecosystem_update(title, message, update_kind=update_kind)
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def publish_material_event(self, kind: str, title: str, message: str, *, critical: bool = False, blocking: bool = False) -> dict[str, Any]:
        """Route a material runtime event into the notification center.

        The event remains outside decision/execution authorization. Critical
        notifications are intentionally not suppressible by normal preferences.
        """
        from core.ecosystem_notifications import NotificationKind

        notification_kind = NotificationKind(str(kind).upper())
        item = self.notifications.publish(
            kind=notification_kind,
            title=title,
            message=message,
            severity=("CRITICAL" if critical else "IMPORTANT"),
            requires_attention=critical or blocking,
            blocking=blocking,
        )
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}
