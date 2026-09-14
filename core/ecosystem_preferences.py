"""User-facing ecosystem preferences kept separate from trading authority.

Preferences control presentation, chart appearance, notifications and analysis
convenience. They never grant execution, risk override, autonomy or security
permission.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class CandleStyle(str, Enum):
    CANDLESTICK = "CANDLESTICK"
    HOLLOW = "HOLLOW"
    OHLC = "OHLC"
    LINE = "LINE"


class CandleColorMode(str, Enum):
    DEFAULT = "DEFAULT"
    CUSTOM = "CUSTOM"
    MONOCHROME = "MONOCHROME"


class ChartTheme(str, Enum):
    DARK = "DARK"
    LIGHT = "LIGHT"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class CandleAppearance:
    style: CandleStyle = CandleStyle.CANDLESTICK
    color_mode: CandleColorMode = CandleColorMode.DEFAULT
    bullish_color: str = "#58d68d"
    bearish_color: str = "#ff7676"
    wick_color: str = "#aab5c8"
    border_enabled: bool = True
    show_wicks: bool = True
    show_bodies: bool = True


@dataclass(frozen=True)
class NotificationPreferences:
    important_enabled: bool = True
    critical_enabled: bool = True
    system_updates_enabled: bool = True
    security_enabled: bool = True
    market_enabled: bool = True
    risk_enabled: bool = True
    connection_enabled: bool = True
    execution_enabled: bool = True
    learning_enabled: bool = True
    recovery_enabled: bool = True
    info_enabled: bool = False


@dataclass(frozen=True)
class EcosystemPreferences:
    default_symbol: str = "EURUSD"
    default_timeframe: str = "5m"
    require_closed_candle: bool = True
    require_filters: bool = True
    chart_theme: ChartTheme = ChartTheme.DARK
    candle: CandleAppearance = CandleAppearance()
    notifications: NotificationPreferences = NotificationPreferences()
    show_technical_details_by_default: bool = False
    psychology_enabled: bool = True
    psychology_data_collection_enabled: bool = True
    autonomous_operation_enabled: bool = False
    real_execution_enabled: bool = False


class EcosystemPreferencesStore:
    """Validated preferences with tenant/subject scoping in trusted request context.

    Local/test callers without a trusted identity retain the original single-user
    behavior. SaaS callers are isolated by the server-injected tenant+subject key.
    """

    def __init__(self, preferences: EcosystemPreferences | None = None) -> None:
        self._default_preferences = preferences or EcosystemPreferences()
        self._validate(self._default_preferences)
        self._scoped: dict[tuple[str, str], EcosystemPreferences] = {}

    @staticmethod
    def _trusted_scope() -> tuple[str, str] | None:
        try:
            from security.http_identity import current_trusted_identity
            identity = current_trusted_identity()
        except Exception:
            identity = None
        if identity is None:
            return None
        tenant_id = str(identity.tenant_id).strip()
        subject_id = str(identity.subject_id).strip()
        if not tenant_id or not subject_id:
            return None
        return tenant_id, subject_id

    def _current(self) -> EcosystemPreferences:
        scope = self._trusted_scope()
        if scope is None:
            return self._default_preferences
        return self._scoped.get(scope, self._default_preferences)

    @property
    def preferences(self) -> EcosystemPreferences:
        return self._current()

    def update(self, **changes) -> EcosystemPreferences:
        current = self._current()
        candidate = replace(current, **changes)
        self._validate(candidate)
        scope = self._trusted_scope()
        if scope is None:
            self._default_preferences = candidate
        else:
            self._scoped[scope] = candidate
        return candidate

    def update_candle(self, **changes) -> EcosystemPreferences:
        current = self._current()
        candle = replace(current.candle, **changes)
        candidate = replace(current, candle=candle)
        self._validate(candidate)
        scope = self._trusted_scope()
        if scope is None:
            self._default_preferences = candidate
        else:
            self._scoped[scope] = candidate
        return candidate

    def update_notifications(self, **changes) -> EcosystemPreferences:
        current = self._current()
        notifications = replace(current.notifications, **changes)
        candidate = replace(current, notifications=notifications)
        self._validate(candidate)
        scope = self._trusted_scope()
        if scope is None:
            self._default_preferences = candidate
        else:
            self._scoped[scope] = candidate
        return candidate

    @staticmethod
    def _validate(value: EcosystemPreferences) -> None:
        if not value.default_symbol.strip():
            raise ValueError("default_symbol is required")
        if not value.default_timeframe.strip():
            raise ValueError("default_timeframe is required")
        if not isinstance(value.psychology_enabled, bool):
            raise ValueError("psychology_enabled must be boolean")
        if not isinstance(value.psychology_data_collection_enabled, bool):
            raise ValueError("psychology_data_collection_enabled must be boolean")
        if value.autonomous_operation_enabled:
            raise ValueError("autonomous operation requires its dedicated authorization flow")
        if value.real_execution_enabled:
            raise ValueError("REAL execution cannot be enabled by preferences")
        if not value.notifications.critical_enabled:
            raise ValueError("critical notifications cannot be disabled")
        for field in (value.candle.bullish_color, value.candle.bearish_color, value.candle.wick_color):
            if not isinstance(field, str) or not field.startswith("#") or len(field) not in (4, 7):
                raise ValueError("candle colors must be hex values")
