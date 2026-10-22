"""Indeed-side response monitor: parse status, derive app_id, collect from ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from indeed_scraper.apply.drafts import app_id_for
from indeed_scraper.apply.status import RESPONSE_STATUSES, response_status_for
from indeed_scraper.apply.statuses import is_submitted_like

from .store import write_response

__all__ = [
    "RESPONSE_STATUSES",
    "app_id_for",
    "collect_responses",
    "parse_status",
]

#: The status the monitor reports for an application whose submit click was
#: dispatched but whose confirmation could not be read.
#:
#: It is deliberately NOT one of the employer-facing statuses
#: ("applied", "viewed", "interview", ...): those describe what the EMPLOYER
#: did, and here we do not know that the employer did anything. The name
#: says exactly what we know - the application went out, the outcome is
#: unknown - so the operator can act on it (check Indeed) without the
#: record making a claim we cannot support.
UNCONFIRMED_STATUS = "unconfirmed"

#: The status the monitor reports for a CONFIRMED application. It is a
#: distinct name from "unconfirmed" for the same reason.
CONFIRMED_STATUS = "applied"


def _now_iso() -> str:
    """The current UTC time, ISO 8601."""
    return datetime.now(tz=timezone.utc).isoformat()


def parse_status(text: str) -> str:
    """Map employer-facing status words to one of RESPONSE_STATUSES.

    The real Indeed vocabulary is understood - an offer, a hire, an
    interview, a rejection, a withdrawal - so `check-responses` tells the
    operator what actually happened.

    An OFFER keeps its own name. Folding it into "interview" would hide the
    one status the operator must act on, which is the whole point of the
    response monitor.

    Defaults to "unknown" when the state cannot be determined.
    """
    return response_status_for(text)


def _status_from_text(text: str) -> str:
    """Internal helper: parse a status string from employer text."""
    return parse_status(text)


def collect_responses(
    ledger_path: Path,
    responses_root: Path,
    *,
    fetch_status=None,
) -> list[dict]:
    """Read the ledger, keep the entries whose application may have gone out,
    derive app_id, and for each produce a response record.

    The kept statuses are the SUBMITTED-LIKE ones: ``submitted`` (the
    employer confirmed it) and ``unconfirmed`` (the click went out, the
    confirmation could not be read). An ``unconfirmed`` application may
    already have reached a real employer, so hiding it from the operator's
    own status report would hide an application they may have to chase.

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

    # Now process the entries whose application may have reached the
    # employer. The vocabulary lives in apply/statuses.py so this filter
    # cannot drift away from the ledger's own definition of the same idea.
    for fingerprint, entry in latest.items():
        status = str(entry.get("status", ""))
        if not is_submitted_like(status):
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
        elif status == "unconfirmed":
            # No live status was read. The application may have gone out,
            # but nothing confirms that the employer received it, so the
            # record says exactly that - it does not claim the employer
            # applied, viewed or interviewed.
            response_status = UNCONFIRMED_STATUS
        else:
            response_status = CONFIRMED_STATUS

        checked_at = _now_iso()

        record = {
            "app_id": app_id,
            "fingerprint": fingerprint,
            "jk": jk,
            "company": company,
            "title": title,
            "checked_at": checked_at,
            "status": response_status,
            # The ledger status is kept beside the reported one, so the
            # operator (and any tooling reading the record) can always see
            # whether this application's submission was confirmed.
            "ledger_status": status,
            "source": "indeed",
        }

        write_response(responses_root, app_id, record)
        records.append(record)

    return records