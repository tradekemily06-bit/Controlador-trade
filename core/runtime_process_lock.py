from __future__ import annotations

from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


class RuntimeProcessLock:
    """Cross-platform exclusive lock preventing two controller runtimes sharing state."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._file = None

    @property
    def is_acquired(self) -> bool:
        """Return whether this instance currently owns the process lock."""
        return self._file is not None

    def acquire(self) -> None:
        if self._file is not None:
            raise RuntimeError("runtime lock já está adquirido nesta instância.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            if not self.path.stat().st_size:
                handle.write("0")
                handle.flush()
            handle.seek(0)
            if msvcrt is not None:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            elif fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # pragma: no cover - unsupported platform
                raise RuntimeError("plataforma sem mecanismo de lock de processo disponível.")
        except BaseException as exc:
            # Any failure after opening the descriptor must close it, including
            # unsupported-platform errors and cancellation during lock setup.
            # Preserve the original exception if descriptor cleanup also fails.
            try:
                handle.close()
            except BaseException:
                pass
            if isinstance(exc, OSError):
                raise RuntimeError(
                    "já existe outra instância do Controlador usando este runtime."
                ) from exc
            raise
        self._file = handle

    def release(self) -> None:
        handle = self._file
        if handle is None:
            return
        try:
            handle.seek(0)
            if msvcrt is not None:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._file = None

    def __enter__(self) -> "RuntimeProcessLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()



def resource_lock_path(resource_path: str | Path) -> Path:
    """Return the canonical sidecar lock path for a shared filesystem resource."""
    resource = Path(resource_path).expanduser().resolve()
    return resource.with_name(resource.name + ".controlador.lock")


class RuntimeProcessLockSet:
    """Acquire the runtime lock and deterministic sidecar locks for shared resources."""

    def __init__(
        self,
        runtime_lock_path: str | Path,
        shared_resource_paths: list[str | Path] | tuple[str | Path, ...] = (),
    ) -> None:
        paths = [Path(runtime_lock_path).expanduser().resolve()]
        paths.extend(resource_lock_path(path) for path in shared_resource_paths)
        # Canonical ordering prevents deadlocks when two processes share overlapping
        # database files but have different runtime directories.
        unique_paths = sorted({path.resolve() for path in paths}, key=str)
        self._locks = [RuntimeProcessLock(path) for path in unique_paths]
        self._acquired: list[RuntimeProcessLock] = []

    @property
    def is_acquired(self) -> bool:
        return len(self._acquired) == len(self._locks) and bool(self._locks)

    def acquire(self) -> None:
        if self._acquired:
            raise RuntimeError("runtime lock set já está adquirido nesta instância.")
        try:
            for lock in self._locks:
                lock.acquire()
                self._acquired.append(lock)
        except BaseException:
            # Roll back even for cancellation (KeyboardInterrupt/SystemExit).
            # Preserve the acquisition failure as the primary error if cleanup
            # also fails; never leave a partially acquired set by interruption.
            try:
                self.release()
            except BaseException:
                pass
            raise

    def release(self) -> None:
        errors: list[Exception] = []
        still_acquired: list[RuntimeProcessLock] = []
        # Attempt every lock in reverse acquisition order. Keep ownership
        # records for descriptors that remain open so a later shutdown/recovery
        # path can retry their release instead of silently losing the handle.
        for lock in reversed(self._acquired):
            try:
                lock.release()
            except Exception as exc:
                errors.append(exc)
                if getattr(lock, "is_acquired", True):
                    still_acquired.append(lock)
        self._acquired = list(reversed(still_acquired))
        if errors:
            raise RuntimeError("falha ao liberar um ou mais locks do runtime.") from errors[0]

    def __enter__(self) -> "RuntimeProcessLockSet":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
