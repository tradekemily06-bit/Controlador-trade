"""Registry for broker-neutral, read-only market-data provider adapters."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from core.active_account_mode import resolve_active_account_mode


@dataclass(frozen=True)
class RegisteredMarketDataProvider:
    provider_id: str
    source: str
    provider: Any


class MarketDataProviderRegistry:
    """Allow multiple broker/provider adapters without coupling analysis to one broker."""

    HEARTBEAT_MAX_AGE_SECONDS = 30
    HEARTBEAT_FUTURE_TOLERANCE_SECONDS = 5

    def __init__(
        self,
        *,
        heartbeat_max_age_seconds: float = HEARTBEAT_MAX_AGE_SECONDS,
        heartbeat_future_tolerance_seconds: float = HEARTBEAT_FUTURE_TOLERANCE_SECONDS,
    ) -> None:
        for name, value, minimum, maximum in (
            ("heartbeat_max_age_seconds", heartbeat_max_age_seconds, 1.0, 3600.0),
            ("heartbeat_future_tolerance_seconds", heartbeat_future_tolerance_seconds, 0.0, 30.0),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < minimum
                or value > maximum
            ):
                raise ValueError(f"{name} must be finite and between {minimum:g} and {maximum:g}")
        self.heartbeat_max_age_seconds = float(heartbeat_max_age_seconds)
        self.heartbeat_future_tolerance_seconds = float(heartbeat_future_tolerance_seconds)
        self._providers: dict[str, RegisteredMarketDataProvider] = {}
        self._selected: str | None = None

    @staticmethod
    def _provider_id(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", value):
            raise ValueError("provider_id inválido")
        return value

    def _heartbeat_is_fresh(self, value: Any) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        try:
            timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                return False
            age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return False
        return (
            -self.heartbeat_future_tolerance_seconds
            <= age
            <= self.heartbeat_max_age_seconds
        )

    def register(self, provider_id: str, provider: Any, source: str) -> None:
        key = self._provider_id(provider_id)
        if provider is None or not callable(getattr(provider, "fetch", None)):
            raise ValueError("provider must implement fetch(request)")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source é obrigatória")
        if key in self._providers:
            raise ValueError("provider_id já registrado")
        self._providers[key] = RegisteredMarketDataProvider(key, source.strip(), provider)
        if self._selected is None and len(self._providers) == 1:
            self._selected = key

    def select(self, provider_id: str) -> RegisteredMarketDataProvider:
        key = self._provider_id(provider_id)
        try:
            provider = self._providers[key]
        except KeyError as exc:
            raise ValueError("provider não registrado") from exc
        self._selected = key
        return provider

    def selected(self) -> RegisteredMarketDataProvider | None:
        return self._providers.get(self._selected) if self._selected else None

    def active_account_mode(self) -> dict[str, Any]:
        selected = self.selected()
        return resolve_active_account_mode(selected.provider if selected else None)

    def status(self, *, probe_account_mode: bool = True) -> dict[str, Any]:
        """Report registration separately from a verified, recent connection heartbeat.

        Frontend readiness polling must be side-effect-free and must not
        initialize/shutdown a broker terminal on every status request.
        """
        account_mode = (
            self.active_account_mode()
            if probe_account_mode
            else {"mode": None, "status": "NOT_PROBED", "execution_authorized": False}
        )
        providers = []
        for item in self._providers.values():
            provider_status = "REGISTERED_NOT_TESTED"
            health: dict[str, Any] = {}
            status_method = getattr(item.provider, "status", None)
            if callable(status_method):
                try:
                    reported = status_method()
                    if isinstance(reported, dict):
                        # Expose only bounded, non-secret connection metadata.
                        health = {
                            key: reported[key]
                            for key in ("connected", "account_mode", "last_seen", "source_id", "stored_candles")
                            if key in reported
                        }
                        if reported.get("connected") is False:
                            provider_status = "DISCONNECTED"
                        elif reported.get("connected") is True:
                            provider_status = (
                                "CONNECTED"
                                if self._heartbeat_is_fresh(reported.get("last_seen"))
                                else "HEARTBEAT_STALE_OR_UNVERIFIED"
                            )
                except Exception:
                    provider_status = "STATUS_ERROR"
            providers.append({
                "provider_id": item.provider_id,
                "source": item.source,
                "status": provider_status,
                "health": health,
                "selected": item.provider_id == self._selected,
                "read_only": True,
                "execution_authorized": False,
            })
        return {
            "selected_provider": self._selected,
            "account_mode": account_mode,
            "providers": providers,
            "count": len(self._providers),
            "provider_registered": bool(self._providers),
        }

    @classmethod
    def from_mapping(
        cls,
        providers: Mapping[str, tuple[Any, str]] | None = None,
        *,
        selected_provider: str | None = None,
    ) -> "MarketDataProviderRegistry":
        registry = cls()
        for provider_id, item in (providers or {}).items():
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("cada provider deve ser um par (provider, source)")
            registry.register(provider_id, item[0], item[1])
        if selected_provider:
            registry.select(selected_provider)
        return registry
