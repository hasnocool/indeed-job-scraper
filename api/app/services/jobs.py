"""Read and query the master job dataset.

The dataset lives in ``data/master/jobs_master.json`` and is written by the
scraper.  The API reuses the scraper's own loader
(``indeed_scraper.export.load_jobs``) and validates the records against its
``Job`` model, so the API and the scraper always agree on what a job is.

The records are returned **verbatim**: the contract requires the exact
fields of the file, with no renaming and no coercion.  The only work done
here is turning missing values into the contract's empty string / empty list.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app import paths
from app.services.cache import FileCache
from indeed_scraper.export import load_jobs

__all__ = [
    "JobQuery",
    "facets",
    "find_by_short_id",
    "list_jobs",
    "load_jobs",
    "load_records",
    "total_jobs",
]

_cache = FileCache()

#: Fields the free-text search runs over.
SEARCH_FIELDS = ("title", "company", "location", "snippet", "salary")

#: Sortable fields, mapped to the key used in the record.
SORT_FIELDS = ("last_seen", "first_seen", "title", "company", "salary")


def load_records(config) -> list[dict[str, Any]]:
    """Every job record of the master dataset, in file order.

    A malformed record is skipped rather than failing the whole response.
    """
    path = paths.master_file(config)

    def loader() -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            records = load_jobs(path)
        except (OSError, ValueError):
            return []
        return [record for record in records if isinstance(record, dict)]

    return _cache.get(path, loader)


def _text(value: Any) -> str:
    """A record field as a string; missing values become ``""``."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _matches(value: Any) -> list[str]:
    """The ``matches`` list; missing or malformed values become ``[]``."""
    if not isinstance(value, (list, tuple)):
        return []
    return [_text(item) for item in value]


def _as_int(value: Any) -> int:
    """``seen_count`` as an int; anything unusable becomes ``0``."""
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


def _normalise(record: dict[str, Any]) -> dict[str, Any]:
    """A record shaped exactly like the contract's ``Job`` object."""
    return {
        "jk": _text(record.get("jk")),
        "title": _text(record.get("title")),
        "company": _text(record.get("company")),
        "location": _text(record.get("location")),
        "salary": _text(record.get("salary")),
        "schedule": _text(record.get("schedule")),
        "posted": _text(record.get("posted")),
        "snippet": _text(record.get("snippet")),
        "url": _text(record.get("url")),
        "matches": _matches(record.get("matches")),
        "fingerprint": _text(record.get("fingerprint")),
        "short_id": _text(record.get("short_id")),
        "status": _text(record.get("status")),
        "first_seen": _text(record.get("first_seen")),
        "last_seen": _text(record.get("last_seen")),
        "seen_count": _as_int(record.get("seen_count")),
        "duplicate_of": _text(record.get("duplicate_of")),
    }


def _contains(haystack: str, needle: str) -> bool:
    """Case-insensitive substring test.

    Both sides are case-folded: the contract promises a case-insensitive
    substring match, so a needle like ``"Port Alberni"`` must still match a
    haystack of ``"port alberni, bc"``.
    """
    return needle.casefold() in haystack.casefold()


def _filter(records: Iterable[dict[str, Any]], query: JobQuery) -> list[dict[str, Any]]:
    """Apply the contract's filters to the records."""
    selected: list[dict[str, Any]] = []
    for record in records:
        job = _normalise(record)

        if query.status and job["status"] != query.status:
            continue
        if query.location and not _contains(job["location"], query.location):
            continue
        if query.company and not _contains(job["company"], query.company):
            continue
        if query.q:
            haystack = " ".join(job[field] for field in SEARCH_FIELDS)
            if not _contains(haystack, query.q):
                continue
        selected.append(job)
    return selected


def _sort_key(job: dict[str, Any], sort: str) -> tuple[Any, ...]:
    """The sort key for one job.

    Strings sort case-insensitively with the text as a tie-breaker so the
    order is stable and predictable for the UI.
    """
    if sort in {"last_seen", "first_seen"}:
        return (_text(job.get(sort)), _text(job.get("title")), _text(job.get("jk")))
    value = _text(job.get(sort))
    return (value.casefold(), value, _text(job.get("title")), _text(job.get("jk")))


def _sort(jobs: list[dict[str, Any]], sort: str, order: str) -> list[dict[str, Any]]:
    """Sort the jobs; ``order`` is ``asc`` or ``desc``."""
    if sort not in SORT_FIELDS:
        sort = "last_seen"
    reverse = order != "asc"
    return sorted(jobs, key=lambda job: _sort_key(job, sort), reverse=reverse)


class JobQuery:
    """The parsed ``GET /api/jobs`` query parameters."""

    __slots__ = ("company", "limit", "location", "offset", "order", "q", "sort", "status")

    def __init__(
        self,
        *,
        q: str = "",
        location: str = "",
        company: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
        sort: str = "last_seen",
        order: str = "desc",
    ) -> None:
        self.q = q.strip()
        self.location = location.strip()
        self.company = company.strip()
        self.status = status.strip()
        self.limit = limit
        self.offset = offset
        self.sort = sort if sort in SORT_FIELDS else "last_seen"
        self.order = order if order in {"asc", "desc"} else "desc"


def list_jobs(config, query: JobQuery) -> tuple[int, list[dict[str, Any]]]:
    """The filtered job page.

    Returns ``(total, items)`` where ``total`` is the count after filtering
    and before pagination.
    """
    matched = _filter(load_records(config), query)
    ordered = _sort(matched, query.sort, query.order)
    page = ordered[query.offset : query.offset + query.limit]
    return len(matched), page


def total_jobs(config) -> int:
    """The unfiltered job count."""
    return len(load_records(config))


def find_by_short_id(config, short_id: str) -> dict[str, Any] | None:
    """One job by its 12-character ``short_id``, or ``None``.

    The dataset may hold several records that share a ``short_id`` (the
    scraper points the later ones at the original with ``duplicate_of``), so
    the first match wins: it is the canonical posting.
    """
    wanted = short_id.strip()
    if not wanted:
        return None
    for record in load_records(config):
        if _text(record.get("short_id")) == wanted:
            return _normalise(record)
    return None


def facets(config) -> dict[str, Any]:
    """The filter values for the UI dropdowns.

    ``locations`` and ``companies`` are sorted alphabetically, de-duplicated
    and exclude empty strings.  ``status_counts`` includes every status
    present in the dataset.
    """
    records = load_records(config)
    locations: set[str] = set()
    companies: set[str] = set()
    status_counts: dict[str, int] = {}
    for record in records:
        location = _text(record.get("location"))
        if location:
            locations.add(location)
        company = _text(record.get("company"))
        if company:
            companies.add(company)
        status = _text(record.get("status"))
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "total": len(records),
        "locations": sorted(locations),
        "companies": sorted(companies),
        "status_counts": dict(sorted(status_counts.items())),
    }


def read_meta(config) -> dict[str, Any]:
    """The ``meta`` block of the master dataset (informational)."""
    path = paths.master_file(config)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    meta = payload.get("meta")
    return meta if isinstance(meta, dict) else {}
