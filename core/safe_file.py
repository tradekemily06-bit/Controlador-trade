"""Race-resistant reads for operational local state files.

The caller is responsible for the appropriate application-level lock. This helper
opens the file itself and validates the opened descriptor, avoiding the
check-then-open TOCTOU pattern used by Path.read_text().
"""
from __future__ import annotations

import os
from pathlib import Path


def read_regular_utf8(path: str | Path, *, max_bytes: int) -> str:
    """Read a regular UTF-8 file through an opened descriptor.

    The descriptor is the authority for the file being read: lstat/path checks
    are not used as a substitute for validating the object actually opened.
    O_NOFOLLOW is required when available so a symlink cannot be followed
    between path resolution and open.
    """
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        raise ValueError("max_bytes inválido.")
    target = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd: int | None = None
    try:
        fd = os.open(target, flags)
        stat = os.fstat(fd)
        if not _is_regular_mode(stat.st_mode):
            raise OSError("arquivo operacional deve ser regular.")
        if stat.st_size > max_bytes:
            raise ValueError("arquivo operacional excede o limite permitido.")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("arquivo operacional excede o limite permitido.")
        return data.decode("utf-8")
    finally:
        if fd is not None:
            os.close(fd)


def _is_regular_mode(mode: int) -> bool:
    return (mode & 0o170000) == 0o100000
