"""User-facing ecosystem preferences kept separate from trading authority.

Preferences control presentation, chart appearance, notifications and analysis
convenience. They never grant execution, risk override, autonomy or security
permission.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from enum import Enum
import json
import os
from pathlib import Path
import tempfile
import threading


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
    autonomous_operation_enabled: bool = False
    real_execution_enabled: bool = False


class EcosystemPreferencesStore:
    """Validated preferences; security-critical permissions are immutable here."""

    def __init__(self, preferences: EcosystemPreferences | None = None, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.RLock()
        self._preferences = self._load() if preferences is None else preferences
        self._validate(self._preferences)
        if preferences is not None and self._path is not None:
            self._persist()

    def _load(self) -> EcosystemPreferences:
        if self._path is None or not self._path.exists():
            return EcosystemPreferences()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("preferences file must contain an object")
            raw = dict(raw)
            candle_raw = raw.pop("candle", {})
            notifications_raw = raw.pop("notifications", {})
            chart_theme = raw.get("chart_theme", ChartTheme.DARK.value)
            if isinstance(chart_theme, str):
                raw["chart_theme"] = ChartTheme(chart_theme.upper())
            candle = CandleAppearance(**candle_raw) if isinstance(candle_raw, dict) else CandleAppearance()
            if isinstance(candle.style, str):
                candle = replace(candle, style=CandleStyle(candle.style.upper()))
            if isinstance(candle.color_mode, str):
                candle = replace(candle, color_mode=CandleColorMode(candle.color_mode.upper()))
            notifications = NotificationPreferences(**notifications_raw) if isinstance(notifications_raw, dict) else NotificationPreferences()
            raw["candle"] = candle
            raw["notifications"] = notifications
            return EcosystemPreferences(**raw)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return EcosystemPreferences()

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self._preferences)
        payload["chart_theme"] = self._preferences.chart_theme.value
        payload["candle"]["style"] = self._preferences.candle.style.value
        payload["candle"]["color_mode"] = self._preferences.candle.color_mode.value
        fd, temporary = tempfile.mkstemp(prefix=".preferences-", suffix=".tmp", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @property
    def preferences(self) -> EcosystemPreferences:
        return self._preferences

    def update(self, **changes) -> EcosystemPreferences:
        with self._lock:
            candidate = replace(self._preferences, **changes)
            self._validate(candidate)
            self._preferences = candidate
            self._persist()
            return candidate

    def update_candle(self, **changes) -> EcosystemPreferences:
        with self._lock:
            candle = replace(self._preferences.candle, **changes)
            candidate = replace(self._preferences, candle=candle)
            self._validate(candidate)
            self._preferences = candidate
            self._persist()
            return candidate

    def update_notifications(self, **changes) -> EcosystemPreferences:
        with self._lock:
            notifications = replace(self._preferences.notifications, **changes)
            candidate = replace(self._preferences, notifications=notifications)
            self._validate(candidate)
            self._preferences = candidate
            self._persist()
            return candidate

    @staticmethod
    def _validate(value: EcosystemPreferences) -> None:
        if not value.default_symbol.strip():
            raise ValueError("default_symbol is required")
        if not value.default_timeframe.strip():
            raise ValueError("default_timeframe is required")
        if value.autonomous_operation_enabled:
            raise ValueError("autonomous operation requires its dedicated authorization flow")
        if value.real_execution_enabled:
            raise ValueError("REAL execution cannot be enabled by preferences")
        if not value.notifications.critical_enabled:
            raise ValueError("critical notifications cannot be disabled")
        for field in (value.candle.bullish_color, value.candle.bearish_color, value.candle.wick_color):
            if not isinstance(field, str) or not field.startswith("#") or len(field) not in (4, 7):
                raise ValueError("candle colors must be hex values")
