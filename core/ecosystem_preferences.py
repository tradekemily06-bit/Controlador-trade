"""Persistent user-facing preferences kept separate from trading authority.

Preferences control presentation, chart appearance, notifications and learning
convenience. They never grant execution, risk override, autonomy or security
permission.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import json
import os
from pathlib import Path
import sqlite3


class CandleStyle(str, Enum):
    CANDLESTICK = "CANDLESTICK"
    HOLLOW = "HOLLOW"
    OHLC = "OHLC"
    LINE = "LINE"


class CandleColorMode(str, Enum):
    DEFAULT = "DEFAULT"
    CUSTOM = "CUSTOM"
    MONOCHROME = "MONOCHROME"


class EcosystemUseMode(str, Enum):
    COCKPIT = "COCKPIT"
    ANALYSIS = "ANALYSIS"
    STUDY = "STUDY"


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
    use_mode: EcosystemUseMode = EcosystemUseMode.COCKPIT
    candle: CandleAppearance = CandleAppearance()
    notifications: NotificationPreferences = NotificationPreferences()
    show_technical_details_by_default: bool = False
    trader_psychology_enabled: bool = True
    autonomous_operation_enabled: bool = False
    real_execution_enabled: bool = False


class EcosystemPreferencesStore:
    """Validated persistent preferences; never an execution-authority store."""

    def __init__(self, preferences: EcosystemPreferences | None = None, database_path: str | None = None) -> None:
        self.database_path = database_path or (
            os.environ.get("CONTROLADOR_PREFERENCES_DB")
            or str(Path(".runtime") / "preferences.sqlite3")
        )
        self._storage_corrupted = False
        loaded = None if preferences is not None else self._load()
        self._preferences = preferences or loaded or EcosystemPreferences()
        self._validate(self._preferences)
        if preferences is not None or not self._storage_corrupted:
            self._save()

    @property
    def preferences(self) -> EcosystemPreferences:
        return self._preferences

    @property
    def storage_corrupted(self) -> bool:
        return self._storage_corrupted

    def update(self, **changes) -> EcosystemPreferences:
        if "autonomous_operation_enabled" in changes or "real_execution_enabled" in changes:
            raise ValueError("execution authority is not configurable through preferences")
        candidate = replace(self._preferences, **changes)
        self._validate(candidate)
        self._preferences = candidate
        self._save()
        return candidate

    def update_candle(self, **changes) -> EcosystemPreferences:
        candle = replace(self._preferences.candle, **changes)
        candidate = replace(self._preferences, candle=candle)
        self._validate(candidate)
        self._preferences = candidate
        self._save()
        return candidate

    def update_notifications(self, **changes) -> EcosystemPreferences:
        notifications = replace(self._preferences.notifications, **changes)
        candidate = replace(self._preferences, notifications=notifications)
        self._validate(candidate)
        self._preferences = candidate
        self._save()
        return candidate

    def _payload(self) -> dict:
        payload = asdict(self._preferences)
        payload["chart_theme"] = self._preferences.chart_theme.value
        payload["use_mode"] = self._preferences.use_mode.value
        payload["candle"]["style"] = self._preferences.candle.style.value
        payload["candle"]["color_mode"] = self._preferences.candle.color_mode.value
        return payload

    def _save(self) -> None:
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._payload(), ensure_ascii=False, sort_keys=True)
        with sqlite3.connect(self.database_path, timeout=5) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS preferences "
                "(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)"
            )
            db.execute(
                "INSERT OR REPLACE INTO preferences(id,payload) VALUES(1,?)",
                (payload,),
            )

    def _load(self) -> EcosystemPreferences | None:
        try:
            with sqlite3.connect(self.database_path, timeout=5) as db:
                row = db.execute("SELECT payload FROM preferences WHERE id=1").fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            if not isinstance(data, dict):
                raise ValueError("preferences payload must be an object")
            candle = data.get("candle", {})
            notifications = data.get("notifications", {})
            if not isinstance(candle, dict) or not isinstance(notifications, dict):
                raise ValueError("invalid nested preferences")
            def strict_bool(mapping: dict, key: str, default: bool) -> bool:
                value = mapping.get(key, default)
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be boolean")
                return value

            notification_values = {
                key: strict_bool(notifications, key, getattr(NotificationPreferences(), key))
                for key in NotificationPreferences.__dataclass_fields__
            }
            return EcosystemPreferences(
                default_symbol=str(data.get("default_symbol", "EURUSD")),
                default_timeframe=str(data.get("default_timeframe", "5m")),
                require_closed_candle=strict_bool(data, "require_closed_candle", True),
                require_filters=strict_bool(data, "require_filters", True),
                chart_theme=ChartTheme(str(data.get("chart_theme", "DARK"))),
                use_mode=EcosystemUseMode(str(data.get("use_mode", "COCKPIT"))),
                candle=CandleAppearance(
                    style=CandleStyle(str(candle.get("style", "CANDLESTICK"))),
                    color_mode=CandleColorMode(str(candle.get("color_mode", "DEFAULT"))),
                    bullish_color=str(candle.get("bullish_color", "#58d68d")),
                    bearish_color=str(candle.get("bearish_color", "#ff7676")),
                    wick_color=str(candle.get("wick_color", "#aab5c8")),
                    border_enabled=strict_bool(candle, "border_enabled", True),
                    show_wicks=strict_bool(candle, "show_wicks", True),
                    show_bodies=strict_bool(candle, "show_bodies", True),
                ),
                notifications=NotificationPreferences(**notification_values),
                show_technical_details_by_default=strict_bool(data, "show_technical_details_by_default", False),
                trader_psychology_enabled=strict_bool(data, "trader_psychology_enabled", True),
                autonomous_operation_enabled=False,
                real_execution_enabled=False,
            )
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError, json.JSONDecodeError):
            self._storage_corrupted = True
            return None

    @staticmethod
    def _validate(value: EcosystemPreferences) -> None:
        if not isinstance(value.default_symbol, str) or not value.default_symbol.strip():
            raise ValueError("default_symbol is required")
        if not isinstance(value.default_timeframe, str) or not value.default_timeframe.strip():
            raise ValueError("default_timeframe is required")
        if not isinstance(value.trader_psychology_enabled, bool):
            raise ValueError("trader_psychology_enabled must be boolean")
        if value.autonomous_operation_enabled:
            raise ValueError("autonomous operation requires its dedicated authorization flow")
        if value.real_execution_enabled:
            raise ValueError("REAL execution cannot be enabled by preferences")
        if not value.notifications.critical_enabled:
            raise ValueError("critical notifications cannot be disabled")
        for field in (
            value.candle.bullish_color,
            value.candle.bearish_color,
            value.candle.wick_color,
        ):
            if (
                not isinstance(field, str)
                or not field.startswith("#")
                or len(field) not in (4, 7)
            ):
                raise ValueError("candle colors must be hex values")
