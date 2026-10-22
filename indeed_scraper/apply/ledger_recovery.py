"""Recovery of a torn (truncated) final ledger line.

The ledger is append-only JSONL. A crash in the middle of an append can leave
a PARTIAL last line: no trailing newline, and the JSON cut off mid-field.

The old parser skipped every malformed line, so a truncated reservation was
dropped entirely. That silently un-reserved the posting: it became invisible
to the idempotency guard and could be applied to a SECOND time - the exact
failure the ledger exists to prevent.

The rule here:

* a truncated FINAL line is recovered as a LIVE reservation. The posting stays
  blocked, because a duplicate application is worse than a missed one. The
  reservation still carries its timestamp, so the normal lease expires it and
  the posting becomes retryable after the lease - the posting is not locked
  out for ever;
* a malformed line in the MIDDLE of the file is skipped, but it is SURFACED
  (a warning), never silently vanished.

This lives in its own module so ``apply/ledger.py`` stays inside the 250-line
house rule.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .budget_day import same_budget_day
from .statuses import SUBMITTED_LIKE_STATUSES as BUDGET_CONSUMING_STATUSES

#: The status a torn reservation is treated as. "reserved" is live (it blocks
#: the posting) and carries the lease, so a genuinely abandoned run still
#: becomes retryable.
TORN_STATUS = "reserved"

#: A torn line's JSON is cut off, so the fields are recovered by pattern.
#: The patterns are deliberately strict: only a plain field name and a plain
#: string value are accepted, never a nested structure.
_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "fingerprint": re.compile(r'"fingerprint"\s*:\s*"([^"\\]*)"'),
    "status": re.compile(r'"status"\s*:\s*"([^"\\]*)"'),
    "applied_at": re.compile(r'"applied_at"\s*:\s*"([^"\\]*)"'),
    "jk": re.compile(r'"jk"\s*:\s*"([^"\\]*)"'),
    "indeed_url": re.compile(r'"indeed_url"\s*:\s*"([^"\\]*)"'),
    "company": re.compile(r'"company"\s*:\s*"([^"\\]*)"'),
    "title": re.compile(r'"title"\s*:\s*"([^"\\]*)"'),
}

#: The statuses that mean the posting must not be applied to again.
_LIVE_STATUSES = frozenset({"reserved", "submitting", "submitted", "unconfirmed"})


def is_truncated_tail(text: str) -> bool:
    """True when the file's last line was cut off by a crash.

    A complete JSONL file ends with a newline. A file that does not was
    either written by something other than this ledger, or its last append
    was interrupted.
    """
    return bool(text) and not text.endswith("\n")


def recover_torn_line(line: str) -> dict[str, Any] | None:
    """Rebuild a reservation from a truncated JSON line.

    Returns a synthetic entry when the line carries a fingerprint - the one
    field the idempotency guard needs - or ``None`` when it does not, in
    which case there is nothing to protect.

    The recovered status is deliberately NOT taken from the torn text: a
    half-written ``"submitt`` could be anything. The posting is treated as
    ``reserved`` (live, and lease-expirable) which is the safe direction: a
    duplicate application is worse than a missed one.
    """
    fingerprint = _FIELD_PATTERNS["fingerprint"].search(line)
    if fingerprint is None:
        return None
    recovered: dict[str, Any] = {
        "fingerprint": fingerprint.group(1),
        "status": TORN_STATUS,
        "detail": "torn_reservation_recovered",
    }
    for name in ("applied_at", "jk", "indeed_url", "company", "title"):
        match = _FIELD_PATTERNS[name].search(line)
        if match is not None:
            recovered[name] = match.group(1)
    return recovered


def parse_line(line: str) -> dict[str, Any] | None:
    """Parse one JSONL line, or return None when it is not a JSON object."""
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def latest_entry(entries: list[dict[str, Any]], fingerprint: str) -> dict[str, Any] | None:
    """The most recent entry for *fingerprint*, or None when it never appeared.

    The ledger is append-only and chronological, so the LAST matching entry
    carries the current status.
    """
    found: dict[str, Any] | None = None
    for entry in entries:
        if entry.get("fingerprint") == fingerprint:
            found = entry
    return found


def latest_status(entries: list[dict[str, Any]], fingerprint: str) -> str | None:
    """The latest status recorded for *fingerprint*."""
    entry = latest_entry(entries, fingerprint)
    if entry is None:
        return None
    status = entry.get("status")
    return status if isinstance(status, str) else None


def metadata_for(entries: list[dict[str, Any]], fingerprint: str) -> dict[str, Any]:
    """The job metadata known for *fingerprint* (from its reservation)."""
    known: dict[str, Any] = {}
    for entry in entries:
        if entry.get("fingerprint") != fingerprint:
            continue
        for key in ("jk", "indeed_url", "company", "title"):
            value = entry.get(key)
            if value:
                known[key] = value
    return known


def latest_by_fingerprint(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The last entry for every fingerprint, keyed by fingerprint."""
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        fingerprint = entry.get("fingerprint")
        if isinstance(fingerprint, str):
            latest[fingerprint] = entry
    return latest


def reservation_age(
    entries: list[dict[str, Any]], fingerprint: str, now: datetime
) -> float | None:
    """Seconds since the posting was reserved, or None if it is not reserved.

    A run that is killed mid-application leaves a "reserved" line behind.
    The caller uses the age to expire that stale reservation, so the posting
    is not blocked forever. A RECOVERED torn reservation carries its
    timestamp too, so the lease expires it as well.
    """
    status = latest_status(entries, fingerprint)
    if status != "reserved":
        return None
    entry = latest_entry(entries, fingerprint)
    if entry is None:
        return None
    stamp = entry.get("applied_at")
    if not isinstance(stamp, str):
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when).total_seconds()


def _parse_stamp(entry: dict[str, Any]) -> datetime | None:
    """The entry's timestamp, as an aware UTC datetime, or None."""
    stamp = entry.get("applied_at")
    if not isinstance(stamp, str):
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def count_budget_consuming(entries: list[dict[str, Any]], moment: datetime) -> int:
    """Count the applications that consumed a slot of the daily budget.

    Each fingerprint counts ONCE, using its LATEST status, so a posting
    marked more than once cannot inflate the count and wrongly block the
    operator's budget.

    The counted statuses are the BUDGET-CONSUMING ones: a confirmed
    submission, and an unconfirmed attempt whose click may already have
    reached the employer. The operator cannot un-send the latter, so the
    budget has to assume it was spent.
    """
    latest = latest_by_fingerprint(entries)
    count = 0
    for entry in latest.values():
        if entry.get("status") not in BUDGET_CONSUMING_STATUSES:
            continue
        when = _parse_stamp(entry)
        if when is None:
            continue
        if same_budget_day(when, moment):
            count += 1
    return count


def latest_budget_consuming_at(entries: list[dict[str, Any]]) -> datetime | None:
    """When the most recent application that may have gone out happened.

    Used to pace the NEXT application. The pacing has to hold across
    runs, and the ledger is the only thing that outlives a process.

    Both submitted-like statuses count: a confirmed submission and an
    unconfirmed attempt. An unconfirmed click may already have reached
    the employer, so pacing only after a confirmed one would let exactly
    the attempts that slipped through go out un-paced.
    """
    latest = latest_by_fingerprint(entries)
    newest: datetime | None = None
    for entry in latest.values():
        if entry.get("status") not in BUDGET_CONSUMING_STATUSES:
            continue
        when = _parse_stamp(entry)
        if when is None:
            continue
        if newest is None or when > newest:
            newest = when
    return newest
