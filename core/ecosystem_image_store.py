"""Safe persistent visual customization for the ecosystem UI."""
from __future__ import annotations

import base64
import binascii
import os
import tempfile
from pathlib import Path


class EcosystemImageStore:
    ALLOWED = {
        "profile": {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"},
        "logo": {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"},
        "background": {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"},
    }
    MAX_BYTES = 5 * 1024 * 1024

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def save(self, kind: str, payload: bytes, mime: str) -> str:
        kind = str(kind).strip().lower()
        if kind not in self.ALLOWED:
            raise ValueError("tipo de imagem inválido")
        mime = str(mime).lower().split(";", 1)[0].strip()
        suffix = self.ALLOWED[kind].get(mime)
        if suffix is None:
            raise ValueError("formato não permitido. Use JPG, PNG ou WebP.")
        if not isinstance(payload, bytes) or not payload or len(payload) > self.MAX_BYTES:
            raise ValueError("a imagem deve ter até 5 MB")
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{kind}{suffix}"
        fd, temporary = tempfile.mkstemp(prefix=f".{kind}-", suffix=".tmp", dir=str(self.directory))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return mime

    def save_data_url(self, kind: str, data_url: str) -> str:
        if not isinstance(data_url, str) or not data_url.startswith("data:"):
            raise ValueError("imagem deve ser um data URL")
        try:
            header, encoded = data_url.split(",", 1)
        except ValueError as exc:
            raise ValueError("data URL inválido") from exc
        if ";base64" not in header.lower():
            raise ValueError("imagem deve usar base64")
        mime = header[5:].split(";", 1)[0].lower()
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("base64 inválido") from exc
        return self.save(kind, payload, mime)

    def read(self, kind: str) -> tuple[bytes, str] | None:
        kind = str(kind).strip().lower()
        if kind not in self.ALLOWED:
            raise ValueError("tipo de imagem inválido")
        for mime, suffix in self.ALLOWED[kind].items():
            target = self.directory / f"{kind}{suffix}"
            if target.exists():
                payload = target.read_bytes()
                if not payload or len(payload) > self.MAX_BYTES:
                    return None
                return payload, mime
        return None
