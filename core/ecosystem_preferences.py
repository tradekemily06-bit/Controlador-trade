"""User-facing ecosystem preferences kept separate from trading authority.

Preferences control presentation, chart appearance, notifications and analysis
convenience. They never grant execution, risk override, autonomy or security
permission.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
from enum import Enum


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
        self.path = Path(path) if path is not None else None
        self._preferences = self._load(path) if preferences is None and path is not None else (preferences or EcosystemPreferences())
        self._validate(self._preferences)

    @classmethod
    def _load(cls, path: str | Path) -> EcosystemPreferences:
        file = Path(path)
        if not file.exists():
            return EcosystemPreferences()
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
            candle = raw.get("candle", {})
            notifications = raw.get("notifications", {})
            defaults = NotificationPreferences()
            return EcosystemPreferences(
                default_symbol=str(raw["default_symbol"]),
                default_timeframe=str(raw["default_timeframe"]),
                require_closed_candle=bool(raw["require_closed_candle"]),
                require_filters=bool(raw["require_filters"]),
                chart_theme=ChartTheme(str(raw["chart_theme"])),
                candle=CandleAppearance(
                    style=CandleStyle(str(candle["style"])),
                    color_mode=CandleColorMode(str(candle["color_mode"])),
                    bullish_color=str(candle["bullish_color"]),
                    bearish_color=str(candle["bearish_color"]),
                    wick_color=str(candle["wick_color"]),
                    border_enabled=bool(candle["border_enabled"]),
                    show_wicks=bool(candle["show_wicks"]),
                    show_bodies=bool(candle["show_bodies"]),
                ),
                notifications=NotificationPreferences(**{
                    name: bool(notifications.get(name, getattr(defaults, name)))
                    for name in NotificationPreferences.__dataclass_fields__
                }),
                show_technical_details_by_default=bool(raw["show_technical_details_by_default"]),
                autonomous_operation_enabled=False,
                real_execution_enabled=False,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("preferências persistidas inválidas") from exc

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(asdict(self._preferences), default=lambda value: value.value, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    @property
    def preferences(self) -> EcosystemPreferences:
        return self._preferences

    def update(self, **changes) -> EcosystemPreferences:
        candidate = replace(self._preferences, **changes)
        self._validate(candidate)
        self._preferences = candidate
        self._persist()
        return candidate

    def update_candle(self, **changes) -> EcosystemPreferences:
        candle = replace(self._preferences.candle, **changes)
        candidate = replace(self._preferences, candle=candle)
        self._validate(candidate)
        self._preferences = candidate
        self._persist()
        return candidate

    def update_notifications(self, **changes) -> EcosystemPreferences:
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
