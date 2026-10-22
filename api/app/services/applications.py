"""The application ledger.

``data/applications/ledger.jsonl`` is an append-only JSONL file written by
the scraper's ``ApplicationLedger``.  It does not exist on a fresh clone, and
a missing file is **not** an error: the endpoints return an empty collection
with HTTP 200.

The ledger is append-only and a posting may be written several times (a job
moves from ``reserved`` to ``submitted``).  The **last** entry for a given
``jk`` wins.
"""

from __future__ import annotations

import json
from typing import Any

from app import paths
from app.services.cache import FileCache
from indeed_scraper.apply.reporting import load_ledger

__all__ = ["list_applications", "load_entries", "summary"]

_cache = FileCache()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def load_entries(config) -> list[dict[str, Any]]:
    """The ledger entries, latest status per job.

    The scraper's own ``load_ledger`` is used to read the file (it already
    skips malformed lines).  A missing file yields an empty list.
    """
    path = paths.ledger_file(config)

    def loader() -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            raw = load_ledger(path)
        except OSError:
            return []

        # The ledger is keyed by fingerprint; the contract's view is keyed by
        # jk, and the last line for a job carries its current status.
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for entry in raw:
            jk = _text(entry.get("jk"))
            key = jk or _text(entry.get("fingerprint"))
            if not key:
                continue
            if key not in latest:
                order.append(key)
            latest[key] = entry
        return [latest[key] for key in order]

    return _cache.get(path, loader)


def _to_entry(record: dict[str, Any]) -> dict[str, Any]:
    """One ledger record shaped like the contract's ``ApplicationEntry``."""
    return {
        "jk": _text(record.get("jk")),
        "company": _text(record.get("company")),
        "title": _text(record.get("title")),
        "status": _text(record.get("status")),
        "at": _text(record.get("applied_at")) or _text(record.get("at")),
        "indeed_url": _text(record.get("indeed_url")) or _text(record.get("url")),
    }


def list_applications(
    config, limit: int, offset: int, status: str = ""
) -> tuple[int, list[dict[str, Any]]]:
    """A page of ledger entries."""
    wanted = status.strip()
    entries = [_to_entry(record) for record in load_entries(config)]
    if wanted:
        entries = [entry for entry in entries if entry["status"] == wanted]
    return len(entries), entries[offset : offset + limit]


def summary(config) -> dict[str, Any]:
    """Counts by ledger status.

    An empty ledger gives ``{"total": 0, "status_counts": {}}``.
    """
    entries = [_to_entry(record) for record in load_entries(config)]
    counts: dict[str, int] = {}
    for entry in entries:
        status = entry["status"]
        if status:
            counts[status] = counts.get(status, 0) + 1
    return {"total": len(entries), "status_counts": dict(sorted(counts.items()))}


def read_raw(config) -> list[dict[str, Any]]:
    """The raw ledger lines, for diagnostics."""
    path = paths.ledger_file(config)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries
