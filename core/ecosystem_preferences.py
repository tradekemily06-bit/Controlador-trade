"""User-facing ecosystem preferences kept separate from trading authority."""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
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
    """Validated preferences, optionally backed by durable scoped state."""

    NAMESPACE = "ecosystem.preferences.v1"

    def __init__(self, preferences: EcosystemPreferences | None = None, *, state_store=None) -> None:
        self._default_preferences = preferences or EcosystemPreferences()
        self._validate(self._default_preferences)
        self._scoped: dict[tuple[str, str], EcosystemPreferences] = {}
        self._state_store = state_store

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
        return (tenant_id, subject_id) if tenant_id and subject_id else None

    def _require_scope_for_durable_state(self) -> tuple[str, str] | None:
        scope = self._trusted_scope()
        if self._state_store is not None and scope is None:
            raise PermissionError("trusted tenant and subject scope are required for durable preferences")
        return scope

    @staticmethod
    def _decode(payload: dict[str, Any]) -> EcosystemPreferences:
        candle = payload.get("candle", {})
        notifications = payload.get("notifications", {})
        return EcosystemPreferences(
            default_symbol=str(payload.get("default_symbol", "EURUSD")),
            default_timeframe=str(payload.get("default_timeframe", "5m")),
            require_closed_candle=bool(payload.get("require_closed_candle", True)),
            require_filters=bool(payload.get("require_filters", True)),
            chart_theme=ChartTheme(str(payload.get("chart_theme", ChartTheme.DARK.value))),
            candle=CandleAppearance(
                style=CandleStyle(str(candle.get("style", CandleStyle.CANDLESTICK.value))),
                color_mode=CandleColorMode(str(candle.get("color_mode", CandleColorMode.DEFAULT.value))),
                bullish_color=str(candle.get("bullish_color", "#58d68d")),
                bearish_color=str(candle.get("bearish_color", "#ff7676")),
                wick_color=str(candle.get("wick_color", "#aab5c8")),
                border_enabled=bool(candle.get("border_enabled", True)),
                show_wicks=bool(candle.get("show_wicks", True)),
                show_bodies=bool(candle.get("show_bodies", True)),
            ),
            notifications=NotificationPreferences(**{k: bool(notifications.get(k, v)) for k, v in asdict(NotificationPreferences()).items()}),
            show_technical_details_by_default=bool(payload.get("show_technical_details_by_default", False)),
            psychology_enabled=bool(payload.get("psychology_enabled", True)),
            psychology_data_collection_enabled=bool(payload.get("psychology_data_collection_enabled", True)),
            autonomous_operation_enabled=bool(payload.get("autonomous_operation_enabled", False)),
            real_execution_enabled=bool(payload.get("real_execution_enabled", False)),
        )

    @staticmethod
    def _encode(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: EcosystemPreferencesStore._encode(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [EcosystemPreferencesStore._encode(item) for item in value]
        return value

    def _current(self) -> EcosystemPreferences:
        scope = self._require_scope_for_durable_state()
        if scope is None:
            return self._default_preferences
        if scope in self._scoped:
            return self._scoped[scope]
        if self._state_store is not None:
            payload = self._state_store.get(tenant_id=scope[0], subject_id=scope[1], namespace=self.NAMESPACE)
            if payload is not None:
                value = self._decode(payload)
                self._validate(value)
                self._scoped[scope] = value
                return value
        return self._default_preferences

    def _fresh_current(self) -> EcosystemPreferences:
        """Reload durable scoped state before a write so stale caches cannot clobber it."""
        scope = self._require_scope_for_durable_state()
        if scope is None or self._state_store is None:
            return self._current()
        payload = self._state_store.get(tenant_id=scope[0], subject_id=scope[1], namespace=self.NAMESPACE)
        if payload is None:
            value = self._default_preferences
        else:
            value = self._decode(payload)
            self._validate(value)
        self._scoped[scope] = value
        return value

    @property
    def preferences(self) -> EcosystemPreferences:
        return self._current()

    def _save(self, value: EcosystemPreferences) -> EcosystemPreferences:
        self._validate(value)
        scope = self._require_scope_for_durable_state()
        if scope is None:
            self._default_preferences = value
        else:
            self._scoped[scope] = value
            if self._state_store is not None:
                self._state_store.put(tenant_id=scope[0], subject_id=scope[1], namespace=self.NAMESPACE, payload=self._encode(asdict(value)))
        return value

    def update(self, **changes) -> EcosystemPreferences:
        return self._save(replace(self._fresh_current(), **changes))

    def update_candle(self, **changes) -> EcosystemPreferences:
        current = self._fresh_current()
        return self._save(replace(current, candle=replace(current.candle, **changes)))

    def update_notifications(self, **changes) -> EcosystemPreferences:
        current = self._fresh_current()
        return self._save(replace(current, notifications=replace(current.notifications, **changes)))

    @staticmethod
    def _validate(value: EcosystemPreferences) -> None:
        if not value.default_symbol.strip() or not value.default_timeframe.strip():
            raise ValueError("default symbol and timeframe are required")
        if not isinstance(value.psychology_enabled, bool) or not isinstance(value.psychology_data_collection_enabled, bool):
            raise ValueError("psychology preferences must be boolean")
        if value.autonomous_operation_enabled:
            raise ValueError("autonomous operation requires its dedicated authorization flow")
        if value.real_execution_enabled:
            raise ValueError("REAL execution cannot be enabled by preferences")
        if not value.notifications.critical_enabled:
            raise ValueError("critical notifications cannot be disabled")
        for field in (value.candle.bullish_color, value.candle.bearish_color, value.candle.wick_color):
            if not isinstance(field, str) or not field.startswith("#") or len(field) not in (4, 7):
                raise ValueError("candle colors must be hex values")
