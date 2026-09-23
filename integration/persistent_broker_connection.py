from __future__ import annotations

from dataclasses import dataclass
import threading
from time import monotonic

from execution.ports import BrokerAdapter


@dataclass(frozen=True)
class BrokerConnectionStatus:
    state: str
    user_disconnected: bool
    adapter_available: bool
    last_check: float | None
    last_error: str | None


class PersistentBrokerConnectionRuntime:
    """Keeps broker availability observable without granting execution authority.

    A manual disconnect is a persistent local latch for the runtime process.
    Reconnect checks happen automatically until the user explicitly disconnects.
    Adapter connect/disconnect calls share one lifecycle lock so a terminal
    cannot be torn down concurrently with initialization.
    """

    def __init__(self, adapter: BrokerAdapter, *, poll_seconds: float = 5.0) -> None:
        if adapter is None:
            raise ValueError("adapter é obrigatório.")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds deve ser positivo.")
        self._adapter = adapter
        self._poll_seconds = float(poll_seconds)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._adapter_lifecycle_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._user_disconnected = False
        self._available = False
        self._last_check: float | None = None
        self._last_error: str | None = None
        self._generation = 0
        self._disconnect_generation: int | None = None

    def start(self) -> None:
        connect = getattr(self._adapter, "connect", None)
        with self._lock:
            self._user_disconnected = False
            self._generation += 1
            generation = self._generation
            self._disconnect_generation = None
            if self._thread is not None and self._thread.is_alive():
                return

        connected = False
        with self._adapter_lifecycle_lock:
            if callable(connect):
                try:
                    connected = bool(connect())
                except Exception:
                    connected = False

        stale_disconnect = False
        should_start_thread = False
        with self._lock:
            stale_start = generation != self._generation or self._user_disconnected
            disconnect_already_handled = self._disconnect_generation == self._generation
            stale_disconnect = connected and stale_start and not disconnect_already_handled
            if not stale_start and not (self._thread is not None and self._thread.is_alive()):
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._run,
                    name="controlador-broker-connection",
                    daemon=True,
                )
                should_start_thread = True

        if stale_disconnect:
            disconnect = getattr(self._adapter, "disconnect", None)
            if callable(disconnect):
                with self._adapter_lifecycle_lock:
                    try:
                        disconnect()
                    except Exception:
                        pass

        if should_start_thread:
            self._thread.start()

    def user_disconnect(self) -> None:
        """Stop automatic reconnect until the user explicitly starts again."""
        with self._lock:
            self._user_disconnected = True
            self._available = False
            self._generation += 1
            self._disconnect_generation = self._generation
        disconnect = getattr(self._adapter, "disconnect", None)
        if callable(disconnect):
            with self._adapter_lifecycle_lock:
                try:
                    disconnect()
                except Exception:
                    pass

    def status(self) -> BrokerConnectionStatus:
        with self._lock:
            if self._user_disconnected:
                state = "USER_DISCONNECTED"
            elif self._available:
                state = "CONNECTED"
            else:
                state = "DISCONNECTED"
            return BrokerConnectionStatus(
                state=state,
                user_disconnected=self._user_disconnected,
                adapter_available=self._available,
                last_check=self._last_check,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                if self._user_disconnected:
                    return
                generation = self._generation
            try:
                available = bool(self._adapter.is_available())
                error = None
            except Exception as exc:
                available = False
                error = f"{type(exc).__name__}: {exc}"
            with self._lock:
                if generation != self._generation or self._user_disconnected:
                    continue
                self._available = available
                self._last_check = monotonic()
                self._last_error = error
            self._stop.wait(self._poll_seconds)
