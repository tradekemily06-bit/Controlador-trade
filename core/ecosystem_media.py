"""Configuration model for user-provided ecosystem images.

The model stores metadata/reference only. Binary image storage belongs to the UI/storage
layer and must enforce type, size, safe decoding, and isolation before persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MediaKind(str, Enum):
    PROFILE = "profile"
    LOGO = "logo"
    BACKGROUND = "background"


ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 5 * 1024 * 1024

@dataclass(frozen=True)
class EcosystemImage:
    image_id: str
    kind: MediaKind
    mime_type: str
    size_bytes: int
    storage_reference: str
    def validate(self) -> None:
        if not self.image_id.strip() or not self.storage_reference.strip():
            raise ValueError("image_identity_required")
        if self.mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise ValueError("unsupported_image_type")
        if self.size_bytes <= 0 or self.size_bytes > MAX_IMAGE_BYTES:
            raise ValueError("image_size_out_of_bounds")
        if self.storage_reference.startswith(("javascript:", "data:", "http:", "https:")):
            raise ValueError("unsafe_storage_reference")
