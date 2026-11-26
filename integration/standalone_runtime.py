"""Persistent, broker-independent startup for the standalone analyst application."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from analysis.decision_store import DecisionStore
from assistant.chat_service import EcosystemAssistant
from assistant.conversation_store import AssistantConversationStore
from core.runtime_process_lock import RuntimeProcessLock
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_identity import configured_fiscal_owner_id
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema
from integration.ecosystem_service import EcosystemService
from integration.standalone_application_factory import build_standalone_application
from integration.standalone_market_analysis import StandaloneMarketAnalysisService
from integration.market_data_provider_registry import MarketDataProviderRegistry
from integration.standalone_market_data_providers import build_configured_market_data_providers
from core.unified_intelligence import UnifiedIntelligence
from core.ecosystem_state_store import EcosystemStateStore
from core.learning_state_store import LearningStateStore
from core.notification_outbox import PersistentNotificationOutbox
from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
from integration.market_timeframe_monitor import MarketTimeframeMonitor


class StandaloneRuntime:
    """Owns one durable single-user runtime and its process-exclusive lock.

    This runtime intentionally does not instantiate MT5, a broker executor or
    the legacy operational runtime. Market-data adapters must be injected and
    validated separately before the Analysis area can produce a market reading.
    """

    def __init__(
        self,
        runtime_dir: str | Path | None = None,
        *,
        market_data_provider=None,
        market_data_source: str | None = None,
        market_data_providers: Mapping[str, tuple[Any, str]] | None = None,
        selected_market_data_provider: str | None = None,
    ) -> None:
        configured_identity = os.getenv("CONTROLADOR_SINGLE_USER_IDENTITY", "").strip()
        if not configured_identity:
            raise RuntimeError("CONTROLADOR_SINGLE_USER_IDENTITY precisa estar configurada")

        self.runtime_dir = Path(
            runtime_dir or os.getenv("CONTROLADOR_RUNTIME_DIR", ".runtime-standalone")
        ).resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.process_lock = RuntimeProcessLock(self.runtime_dir / "standalone-app.lock")
        self.process_lock.acquire()
        self.closed = False

        try:
            fiscal_database = self.runtime_dir / "fiscal-reserve.sqlite3"

            # The process lock must be held before migrations or repositories
            # touch the shared SQLite runtime.
            self.fiscal_owner_id = migrate_fiscal_schema(str(fiscal_database))
            self.fiscal_reserve = FiscalReserve(str(fiscal_database))
            self.foreign_pending = FiscalPendingQueue(str(fiscal_database))
            self.domestic_pending = FiscalDomesticPendingQueue(str(fiscal_database))

            ecosystem_state_store = EcosystemStateStore(
                self.runtime_dir / "ecosystem-state.sqlite3"
            )
            self.notification_outbox = PersistentNotificationOutbox(
                self.runtime_dir / "notification-outbox.sqlite3"
            )
            self.ecosystem_service = EcosystemService(
                decision_store=DecisionStore(str(self.runtime_dir / "decision-memory.sqlite3")),
                learning_state_store=LearningStateStore(ecosystem_state_store),
                notification_state_store=ecosystem_state_store,
                notification_outbox=self.notification_outbox,
            )
            self.intelligence = UnifiedIntelligence(
                senior_context=self.ecosystem_service.senior_context
            )
            provider_map = dict(market_data_providers or {})
            configured_provider = (
                selected_market_data_provider
                or os.getenv("CONTROLADOR_MARKET_DATA_PROVIDER", "").strip()
                or None
            )
            if not provider_map and market_data_provider is None:
                provider_map = build_configured_market_data_providers(configured_provider)
            if market_data_provider is not None:
                if provider_map:
                    raise ValueError("use market_data_provider or market_data_providers, not both")
                if not isinstance(market_data_source, str) or not market_data_source.strip():
                    raise ValueError("market_data_source is required when a provider is injected")
                provider_map["default"] = (market_data_provider, market_data_source)
            selected_provider = configured_provider
            self.market_data_registry = MarketDataProviderRegistry.from_mapping(
                provider_map,
                selected_provider=selected_provider,
            )
            self.market_analysis_service = None
            self.market_monitor = None
            selected = self.market_data_registry.selected()
            if selected is not None:
                self.market_analysis_service = StandaloneMarketAnalysisService(
                    provider=selected.provider,
                    source=selected.source,
                    intelligence=self.intelligence,
                )

                def publish_market_change(event: dict[str, Any]) -> None:
                    result = event["result"]
                    signal = str(result.get("signal", "AGUARDAR"))
                    previous = event.get("previous_signal")
                    if signal == previous:
                        return
                    if signal == "AGUARDAR" and previous in (None, "AGUARDAR"):
                        return
                    symbol = event["symbol"]
                    timeframe = event["timeframe"]
                    candle_at = event["candle_at"]
                    notification = EcosystemNotification(
                        notification_id=f"market:{symbol}:{timeframe}:{candle_at}:{signal}",
                        kind=NotificationKind.MARKET,
                        severity=NotificationSeverity.IMPORTANT,
                        title=f"Mudança de sinal: {symbol} {timeframe} — {signal}",
                        message=(
                            f"O ciclo {timeframe} de {symbol} foi atualizado. Sinal: {signal}. "
                            "Revisão manual necessária; nenhuma ordem foi enviada."
                        ),
                        requires_attention=True,
                    )
                    self.ecosystem_service.publish_notification(notification)

                self.market_monitor = MarketTimeframeMonitor(
                    self.runtime_dir / "market-timeframe-monitor.sqlite3",
                    self.market_analysis_service,
                    on_result=publish_market_change,
                )
                self.market_monitor.start()
            self.conversation_store = AssistantConversationStore(
                self.runtime_dir / "assistant-conversations.sqlite3"
            )
            self.assistant = EcosystemAssistant(
                store=self.conversation_store,
                service=self.ecosystem_service,
                fiscal=self.fiscal_reserve,
                fiscal_pending_queue=self.foreign_pending,
                fiscal_domestic_pending_queue=self.domestic_pending,
            )
            self.application = build_standalone_application(
                ecosystem_service=self.ecosystem_service,
                fiscal_reserve=self.fiscal_reserve,
                fiscal_owner_id=self.fiscal_owner_id,
                foreign_pending=self.foreign_pending,
                domestic_pending=self.domestic_pending,
                assistant=self.assistant,
                trusted_identity=configured_identity,
                intelligence=self.intelligence,
                market_analyzer=self.market_analysis_service,
                market_data_registry=self.market_data_registry,
            )
        except Exception:
            monitor = getattr(self, "market_monitor", None)
            if monitor is not None:
                monitor.stop()
            self.process_lock.release()
            self.closed = True
            raise

    @classmethod
    def from_environment(cls) -> "StandaloneRuntime":
        return cls()

    def close(self) -> None:
        if self.closed:
            return
        if self.market_monitor is not None:
            self.market_monitor.stop()
        self.process_lock.release()
        self.closed = True

    def __enter__(self) -> "StandaloneRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
