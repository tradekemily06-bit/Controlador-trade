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
        self._thread: threading.Thread | None = None
        self._user_disconnected = False
        self._available = False
        self._last_check: float | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        with self._lock:
            self._user_disconnected = False
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="controlador-broker-connection",
                daemon=True,
            )
            self._thread.start()

    def user_disconnect(self) -> None:
        """Stop automatic reconnect until the user explicitly starts again."""
        with self._lock:
            self._user_disconnected = True
            self._available = False

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
            try:
                available = bool(self._adapter.is_available())
                error = None
            except Exception as exc:
                available = False
                error = f"{type(exc).__name__}: {exc}"
            with self._lock:
                self._available = available
                self._last_check = monotonic()
                self._last_error = error
            self._stop.wait(self._poll_seconds)
