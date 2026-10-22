"""Scrape-run history.

Each run writes ``data/runs/jobs_<stamp>.json`` with a ``meta`` block and the
jobs it found.  The API reuses the scraper's own run-file discovery
(``indeed_scraper.organize.replay.scan_runs``) and loader
(``indeed_scraper.export.load_jobs``).

Runs are returned newest first.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.cache import FileCache
from indeed_scraper.organize.replay import scan_runs

__all__ = ["list_runs", "load_runs"]

_cache = FileCache()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _locations(meta: dict[str, Any]) -> list[str]:
    """The locations a run searched.

    Older run files recorded a single ``location``; newer ones record a
    ``locations`` list.  Both are accepted.
    """
    raw = meta.get("locations")
    if isinstance(raw, (list, tuple)):
        return [_text(item) for item in raw if _text(item)]
    single = meta.get("location")
    if single:
        return [_text(single)]
    return []


def _read_meta(path) -> dict[str, Any]:
    """The ``meta`` block of one run file; ``{}`` when it is missing."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    meta = payload.get("meta")
    return meta if isinstance(meta, dict) else {}


def load_runs(config) -> list[dict[str, Any]]:
    """Every run, newest first."""
    files = scan_runs(config.runs_dir)
    runs: list[dict[str, Any]] = []
    for path in files:
        meta = _read_meta(path)
        runs.append(
            {
                "file": path.name,
                "scraped_at": _text(meta.get("scraped_at")),
                "query": _text(meta.get("query")),
                "locations": _locations(meta),
                "pages_fetched": _as_int(meta.get("pages_fetched")),
                "total_jobs": _as_int(meta.get("total_jobs")),
                "stopped_reason": _text(meta.get("stopped_reason")),
            }
        )
    # Newest first: the file names carry the run's stamp, and ``scraped_at``
    # is the run's own timestamp.  The stamp sorts reliably, so it is the
    # primary key and ``scraped_at`` only breaks ties.
    runs.sort(key=lambda run: (run["file"], run["scraped_at"]), reverse=True)
    return runs


def list_runs(config, limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]:
    """A page of runs, newest first."""
    runs = load_runs(config)
    return len(runs), runs[offset : offset + limit]
