"""Indeed-side response monitor: parse status, derive app_id, collect from ledger."""

from __future__ import annotations

import json
from pathlib import Path

from .store import write_response

RESPONSE_STATUSES = ("applied", "viewed", "interview", "rejected", "withdrawn", "unknown")


from indeed_scraper.apply.drafts import (
    app_id_for,
)


def parse_status(text: str) -> str:
    """Map employer-facing status words to one of RESPONSE_STATUSES.

    Defaults to "unknown" when the state cannot be determined.
    """
    lowered = text.strip().lower()
    if lowered == "interview scheduled":
        return "interview"
    if lowered == "application viewed":
        return "viewed"
    if lowered == "we have decided not to move forward":
        return "rejected"
    if lowered == "":
        return "unknown"
    return "unknown"


def _status_from_text(text: str) -> str:
    """Internal helper: parse a status string from employer text."""
    return parse_status(text)


def collect_responses(
    ledger_path: Path,
    responses_root: Path,
    *,
    fetch_status=None,
) -> list[dict]:
    """Read the ledger, keep only entries whose latest status is "submitted",
    derive app_id, and for each produce a response record.

    *fetch_status* is an optional callable (jk: str) -> str | None used to
    obtain the live status text for a job; when it is None, the status is
    "unknown" and the record is still written.

    Each record is written with write_response() and the list of records
    is returned.
    """
    if not ledger_path.is_file():
        return []

    records: list[dict] = []

    try:
        raw = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines = raw.splitlines()
    # Track latest status per fingerprint
    latest: dict[str, dict] = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # Skip malformed JSON lines without raising
            continue

        # Ensure required fields exist
        fingerprint = entry.get("fingerprint")
        jk = entry.get("jk")
        status = entry.get("status")
        company = entry.get("company", "")
        title = entry.get("title", "")

        if fingerprint is None or jk is None or status is None:
            continue

        # Keep only the latest entry per fingerprint
        if fingerprint in latest:
            # Entries are ordered chronologically in the ledger;
            # later entries overwrite earlier ones.
            latest[fingerprint] = entry
        else:
            latest[fingerprint] = entry

    # Now process only entries whose latest status is "submitted"
    for fingerprint, entry in latest.items():
        status = entry.get("status", "")
        if status != "submitted":
            continue

        app_id = app_id_for(fingerprint)
        jk = entry.get("jk", "")
        company = entry.get("company", "")
        title = entry.get("title", "")

        # Optionally fetch live status text
        if fetch_status is not None:
            live_text = fetch_status(jk)
        else:
            live_text = None

        # Determine the response status from live text
        if live_text is not None and live_text.strip():
            response_status = parse_status(live_text)
        else:
            response_status = "unknown"

        checked_at = entry.get("checked_at", "")

        record = {
            "app_id": app_id,
            "fingerprint": fingerprint,
            "jk": jk,
            "company": company,
            "title": title,
            "checked_at": checked_at,
            "status": response_status,
            "source": "indeed",
        }

        write_response(responses_root, app_id, record)
        records.append(record)

    return records