from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path


class ExternalExecutionRegistry:
    """Durable binding between internal request IDs and broker external IDs.

    The registry is control-plane evidence: it never authorizes execution.
    Mutations are serialized across processes so two workers cannot bind the
    same external identity concurrently.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_name(f".{self.path.name}.lock")
        self._bindings: dict[str, dict[str, str]] = {}
        self._load()

    @contextmanager
    def _process_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._lock_path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def _read_bindings(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("registro external_id inválido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("registro external_id inválido.")

        bindings: dict[str, dict[str, str]] = {}
        seen: set[tuple[str, str]] = set()
        for request_id, item in payload.items():
            if not isinstance(request_id, str) or not request_id.strip() or not isinstance(item, dict):
                raise ValueError("registro external_id inválido.")
            broker = item.get("broker")
            external_id = item.get("external_id")
            if (
                not isinstance(broker, str)
                or not broker.strip()
                or not isinstance(external_id, str)
                or not external_id.strip()
            ):
                raise ValueError("registro external_id inválido.")
            key = (broker.casefold(), external_id)
            if key in seen:
                raise ValueError("external_id duplicado no mesmo broker.")
            seen.add(key)
            bindings[request_id] = {"broker": broker, "external_id": external_id}
        return bindings

    def _load(self) -> None:
        self._bindings = self._read_bindings()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        tmp.write_text(
            json.dumps(self._bindings, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        with tmp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)

    def bind(self, request_id: str, broker: str, external_id: str) -> None:
        if not all(isinstance(v, str) and v.strip() for v in (request_id, broker, external_id)):
            raise ValueError("binding external inválido.")

        with self._process_lock():
            self._load()
            existing = self._bindings.get(request_id)
            candidate = {"broker": broker, "external_id": external_id}
            if existing is not None and existing != candidate:
                raise ValueError("request_id já está ligado a outra execução externa.")
            for other_id, item in self._bindings.items():
                if (
                    other_id != request_id
                    and item["broker"].casefold() == broker.casefold()
                    and item["external_id"] == external_id
                ):
                    raise ValueError("external_id já pertence a outro request_id.")
            self._bindings[request_id] = candidate
            self._write()

    def get(self, request_id: str) -> tuple[str, str] | None:
        with self._process_lock():
            self._load()
            item = self._bindings.get(request_id)
            return None if item is None else (item["broker"], item["external_id"])
