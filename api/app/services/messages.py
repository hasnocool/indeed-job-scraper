"""Sent Indeed messages.

``data/messages/sent.jsonl`` is an append-only JSONL log written by the
scraper's message store.  One object per line:

``conversation_id``, ``company``, ``kind``, ``status``, ``body``, ``detail``,
``at``.

Messages are returned newest first.  The body may be long -- the frontend
renders it as pre-wrap text.
"""

from __future__ import annotations

import json
from typing import Any

from app import paths
from app.services.cache import FileCache

__all__ = ["list_messages", "load_messages"]

_cache = FileCache()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def load_messages(config) -> list[dict[str, Any]]:
    """Every message, newest first."""
    path = paths.messages_file(config)

    def loader() -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                # A partially written line is skipped, not fatal.
                continue
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    return _cache.get(path, loader)


def _to_entry(record: dict[str, Any]) -> dict[str, Any]:
    """One message shaped like the contract's ``MessageEntry``."""
    return {
        "conversation_id": _text(record.get("conversation_id")),
        "company": _text(record.get("company")),
        "kind": _text(record.get("kind")),
        "status": _text(record.get("status")),
        "body": _text(record.get("body")),
        "detail": _text(record.get("detail")),
        "at": _text(record.get("at")),
    }


def list_messages(config, limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]:
    """A page of messages, newest first."""
    entries = [_to_entry(record) for record in load_messages(config)]
    entries.reverse()  # the log is append-only, so the newest entry is last
    return len(entries), entries[offset : offset + limit]
