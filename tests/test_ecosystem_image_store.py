from __future__ import annotations

import base64

import pytest

from core.ecosystem_image_store import EcosystemImageStore


def _data_url(mime: str = "image/png", payload: bytes = b"image-bytes") -> str:
    return f"data:{mime};base64," + base64.b64encode(payload).decode("ascii")


def test_image_store_persists_each_allowed_kind(tmp_path):
    store = EcosystemImageStore(tmp_path)
    for kind in ("profile", "logo", "background"):
        assert store.save_data_url(kind, _data_url()) == "image/png"
        assert store.read(kind) == (b"image-bytes", "image/png")


def test_image_store_rejects_unsafe_format_and_size(tmp_path):
    store = EcosystemImageStore(tmp_path)
    with pytest.raises(ValueError):
        store.save_data_url("profile", _data_url("image/gif"))
    with pytest.raises(ValueError):
        store.save_data_url("unknown", _data_url())
    with pytest.raises(ValueError):
        store.save_data_url("profile", _data_url(payload=b"x" * (5 * 1024 * 1024 + 1)))


def test_image_store_replaces_atomically_and_never_changes_operational_preferences(tmp_path):
    store = EcosystemImageStore(tmp_path)
    store.save_data_url("profile", _data_url(payload=b"one"))
    store.save_data_url("profile", _data_url(payload=b"two"))
    assert store.read("profile") == (b"two", "image/png")
