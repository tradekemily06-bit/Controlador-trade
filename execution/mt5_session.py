from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from weakref import WeakKeyDictionary
from typing import Any, Iterator


class MT5SessionConflict(RuntimeError):
    """Raised when a different MT5 account mode already owns the module session."""


class MT5SessionCoordinator:
    """Own one MetaTrader5 Python-module session and prevent mode races.

    The MetaTrader5 Python API exposes one connection lifecycle per imported
    module object. Adapters therefore cannot independently call initialize()
    and shutdown() while another adapter is using the same module. This
    coordinator reference-counts owners, serializes operations and rejects a
    DEMO/REAL mode switch while the current session still has owners.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._initialized = False
        self._mode: str | None = None
        self._owners: dict[str, int] = {}
        self._module: Any = None

    def acquire(self, module: Any, *, mode: str, owner: str) -> bool:
        normalized_mode = str(mode).strip().upper()
        if normalized_mode not in {"DEMO", "REAL"}:
            raise ValueError("modo MT5 inválido.")
        if not owner:
            raise ValueError("owner MT5 obrigatório.")

        with self._lock:
            if self._initialized:
                if self._module is not module:
                    raise MT5SessionConflict("módulo MT5 diferente já possui a sessão ativa.")
                if self._mode != normalized_mode:
                    return False
                self._owners[owner] = self._owners.get(owner, 0) + 1
                return True

            if not bool(module.initialize()):
                return False

            self._initialized = True
            self._module = module
            self._mode = normalized_mode
            self._owners = {owner: 1}
            return True

    def release(self, module: Any, *, owner: str) -> None:
        with self._lock:
            if not self._initialized or self._module is not module:
                return
            count = self._owners.get(owner)
            if count is None:
                return
            if count > 1:
                self._owners[owner] = count - 1
                return
            self._owners.pop(owner, None)
            if self._owners:
                return
            try:
                module.shutdown()
            finally:
                self._initialized = False
                self._module = None
                self._mode = None

    @contextmanager
    def operation(self, module: Any, *, mode: str, owner: str) -> Iterator[None]:
        normalized_mode = str(mode).strip().upper()
        with self._lock:
            if (
                not self._initialized
                or self._module is not module
                or self._mode != normalized_mode
                or self._owners.get(owner, 0) <= 0
            ):
                raise MT5SessionConflict(
                    "sessão MT5 não pertence ao adapter; operação bloqueada."
                )
            yield

    def is_owned(self, module: Any, *, owner: str) -> bool:
        with self._lock:
            return self._initialized and self._module is module and self._owners.get(owner, 0) > 0

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": "CONNECTED" if self._initialized else "DISCONNECTED",
                "mode": self._mode,
                "owners": len(self._owners),
            }


_coordinators: WeakKeyDictionary[Any, MT5SessionCoordinator] = WeakKeyDictionary()
_fallback_coordinators: dict[int, tuple[Any, MT5SessionCoordinator]] = {}
_registry_lock = RLock()


def coordinator_for(module: Any) -> MT5SessionCoordinator:
    """Return the coordinator shared by all adapters using the same module."""
    with _registry_lock:
        try:
            coordinator = _coordinators.get(module)
            if coordinator is None:
                coordinator = MT5SessionCoordinator()
                _coordinators[module] = coordinator
            return coordinator
        except TypeError:
            # Some test doubles/proxy objects are not weak-referenceable.
            key = id(module)
            entry = _fallback_coordinators.get(key)
            if entry is not None and entry[0] is module:
                return entry[1]
            coordinator = MT5SessionCoordinator()
            _fallback_coordinators[key] = (module, coordinator)
            return coordinator
