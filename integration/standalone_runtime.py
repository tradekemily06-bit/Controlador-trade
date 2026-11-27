"""Persistent, broker-independent startup for the standalone analyst application."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from analysis.decision_store import DecisionStore
from assistant.chat_service import EcosystemAssistant
from assistant.conversation_store import AssistantConversationStore
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState
from security.tenant_scoped_decision_memory import TenantScopedDecisionMemory
from integration.tenant_notification_dispatcher import TenantNotificationDispatcher
from core.runtime_process_lock import RuntimeProcessLock
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_identity import configured_fiscal_owner_id
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
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
from core.sqlite_backup_service import SQLiteBackupService
from core.tenant_fiscal_backup import TenantFiscalBackupService
from core.sqlite_backup_scheduler import SQLiteBackupScheduler
from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
from integration.market_timeframe_monitor import MarketTimeframeMonitor
from integration.notification_outbox_worker import NotificationOutboxWorker
from integration.rss_news_provider import RSSNewsProvider


# Failed startup workers may be blocked in an external provider/sink. Retain
# their references and the process lock until process exit rather than allowing
# a second runtime to open the same SQLite files concurrently.
_FAILED_STARTUP_LOCKS: list[tuple[Any, tuple[Any, str], ...]] = []
_FAILED_STARTUP_LOCKS_GUARD = threading.Lock()


def _release_failed_startup_lock_when_safe(
    process_lock: Any, workers: tuple[tuple[Any, str], ...]
) -> None:
    # The failed constructor has no runtime object left to call close() again.
    # A small daemon reaper releases the OS lock only after every worker is
    # confirmed stopped; status errors deliberately keep the lock held.
    while True:
        try:
            if all(
                worker.status().get(running_key) is False
                for worker, running_key in workers
            ):
                process_lock.release()
                with _FAILED_STARTUP_LOCKS_GUARD:
                    _FAILED_STARTUP_LOCKS[:] = [
                        item for item in _FAILED_STARTUP_LOCKS
                        if item[0] is not process_lock
                    ]
                return
        except Exception:
            pass
        time.sleep(0.25)


def _stop_workers_and_report_active(workers: tuple[tuple[Any, str], ...]) -> list[str]:
    still_running: list[str] = []
    for worker, running_key in workers:
        if worker is None:
            continue
        worker.stop()
        status = worker.status()
        if status.get(running_key) is not False:
            still_running.append(type(worker).__name__)
    return still_running


def _cleanup_failed_startup(process_lock: Any, workers: tuple[tuple[Any, str], ...]) -> list[str]:
    try:
        still_running = _stop_workers_and_report_active(workers)
    except Exception:
        # A failed stop/status check is not proof that the worker exited.
        still_running = [
            type(worker).__name__
            for worker, _ in workers
            if worker is not None
        ]
    if still_running:
        # Keep strong references: closing the lock file would release the OS
        # lock while a background worker may still use SQLite.
        retained_workers = tuple(
            (worker, running_key) for worker, running_key in workers if worker is not None
        )
        with _FAILED_STARTUP_LOCKS_GUARD:
            _FAILED_STARTUP_LOCKS.append((process_lock, retained_workers))
        threading.Thread(
            target=_release_failed_startup_lock_when_safe,
            args=(process_lock, retained_workers),
            name="standalone-failed-startup-lock-reaper",
            daemon=True,
        ).start()
    else:
        process_lock.release()
    return still_running


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
        notification_sink=None,
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
            tenant_storage = SQLiteTenantStorage(
                self.runtime_dir / "tenant-state.sqlite3"
            )
            self.tenant_state = TenantScopedEcosystemState(tenant_storage)
            self.tenant_decision_memory = TenantScopedDecisionMemory(tenant_storage)
            self.local_tenant_context = TenantContext(
                tenant_id="local-single-user",
                subject_id=configured_identity,
            )
            # Prepared owner-sharded fiscal repositories are available as an
            # internal primitive; remote HTTP requests remain fail-closed until
            # trusted identity, durable storage and recovery are production-ready.
            self.tenant_fiscal_store_factory = TenantFiscalStoreFactory(self.runtime_dir)
            # Available to trusted, explicitly addressed event producers.
            # No global broadcast or automatic legacy-event migration occurs.
            self.tenant_notification_dispatcher = TenantNotificationDispatcher(
                self.tenant_state
            )
            self.notification_outbox = PersistentNotificationOutbox(
                self.runtime_dir / "notification-outbox.sqlite3"
            )
            self.notification_worker = None
            if notification_sink is not None:
                self.notification_worker = NotificationOutboxWorker(
                    self.notification_outbox, notification_sink
                )
                self.notification_worker.start()
            self.backup_scheduler = None
            backup_enabled = os.getenv(
                "CONTROLADOR_AUTOMATIC_BACKUP_ENABLED", ""
            ).strip().lower() in {"1", "true", "yes"}
            if backup_enabled:
                backup_dir_value = os.getenv("CONTROLADOR_BACKUP_DIR", "").strip()
                if not backup_dir_value:
                    raise RuntimeError(
                        "CONTROLADOR_BACKUP_DIR é obrigatório quando backups automáticos estão habilitados"
                    )
                interval_value = os.getenv(
                    "CONTROLADOR_BACKUP_INTERVAL_SECONDS", "86400"
                ).strip()
                try:
                    backup_interval = int(interval_value)
                except ValueError as exc:
                    raise RuntimeError(
                        "CONTROLADOR_BACKUP_INTERVAL_SECONDS deve ser um inteiro"
                    ) from exc
                backup_service = SQLiteBackupService(
                    self.runtime_dir, backup_dir_value
                )
                tenant_fiscal_backup_service = TenantFiscalBackupService(
                    self.tenant_fiscal_store_factory, backup_dir_value
                )
                self.backup_scheduler = SQLiteBackupScheduler(
                    backup_service,
                    additional_backup_services=(tenant_fiscal_backup_service,),
                    interval_seconds=backup_interval,
                )
                self.backup_scheduler.start()
            self.ecosystem_service = EcosystemService(
                decision_store=DecisionStore(str(self.runtime_dir / "decision-memory.sqlite3")),
                learning_state_store=LearningStateStore(ecosystem_state_store),
                notification_state_store=ecosystem_state_store,
                notification_outbox=self.notification_outbox,
                news_provider=RSSNewsProvider.from_environment(),
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
            if configured_provider == "icmarkets_mt5_demo":
                configured_provider = "mt5_demo"
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
            self.mt5_relay_store = (
                selected.provider if selected is not None and selected.provider_id == "mt5_relay" else None
            )
            if selected is not None:
                self.market_analysis_service = StandaloneMarketAnalysisService(
                    provider=selected.provider,
                    source=selected.source,
                    intelligence=self.intelligence,
                    decision_sink=lambda record, context=None: self.tenant_decision_memory.save(
                        context or self.local_tenant_context, record
                    ),
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
                    # Deliver only to the owner bound to this subscription.
                    # Never write a remote user's event to the legacy global inbox.
                    self.tenant_notification_dispatcher.publish(
                        event["tenant_context"], notification
                    )

                self.market_monitor = MarketTimeframeMonitor(
                    self.runtime_dir / "market-timeframe-monitor.sqlite3",
                    self.market_analysis_service,
                    on_result=publish_market_change,
                    default_context=self.local_tenant_context,
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
            workers = (
                (getattr(self, "market_monitor", None), "worker_running"),
                (getattr(self, "notification_worker", None), "running"),
                (getattr(self, "backup_scheduler", None), "worker_running"),
            )
            still_running = _cleanup_failed_startup(self.process_lock, workers)
            if not still_running:
                self.closed = True
            raise

    @classmethod
    def from_environment(cls) -> "StandaloneRuntime":
        return cls()

    def close(self) -> None:
        if self.closed:
            return

        # Never release the process-exclusive runtime lock while a background
        # worker is still executing. A blocked provider/sink must not allow a
        # second runtime to open the same SQLite state concurrently.
        workers = (
            (self.market_monitor, "worker_running"),
            (self.notification_worker, "running"),
            (self.backup_scheduler, "worker_running"),
        )
        still_running = _stop_workers_and_report_active(workers)

        if still_running:
            names = ", ".join(sorted(still_running))
            raise RuntimeError(
                "runtime shutdown aguardando workers ativos: " + names
            )

        self.process_lock.release()
        self.closed = True

    def __enter__(self) -> "StandaloneRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
