"""A tiny mtime-keyed cache for the file-backed services.

The scraper rewrites its state files rarely, so the API can re-read them only
when they actually change.  The cache key is the file's ``(mtime, size)`` so
an edited file is picked up immediately, and a missing file stays missing
without being cached forever.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

__all__ = ["FileCache"]

T = TypeVar("T")


class FileCache:
    """Cache one value per file, invalidated when the file changes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[Path, tuple[tuple[float, int] | None, T]] = {}

    @staticmethod
    def _stamp(path: Path) -> tuple[float, int] | None:
        """The file's identity: mtime and size, or ``None`` when it is absent."""
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime, stat.st_size)

    def get(self, path: Path, loader: Callable[[], T]) -> T:
        """Return the cached value for ``path``, calling ``loader`` when stale."""
        key = path
        stamp = self._stamp(path)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] == stamp:
                return entry[1]
        value = loader()
        with self._lock:
            self._entries[key] = (stamp, value)
        return value

    def clear(self) -> None:
        """Drop every cached value."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment flag."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}
