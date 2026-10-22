"""Read the status of the applications already on Indeed.

Indeed tracks the candidate's own applications (``myjobs.indeed.com/applied``)
with a status per application: Applied, Interviewing, Offer received, Hired,
No longer interested, and the employer's own outcomes (Not selected by
employer, Job closed or expired on Indeed).

This module READS that status and mirrors it into the local ledger, so the
answer to "what is happening with my applications" lives in one place, and an
offer that Indeed has recorded is surfaced to the operator instead of being
acted on automatically.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import IndeedScraperError

__all__ = [
    "ACTION_REQUIRED",
    "TRACKER_STATUSES",
    "TrackerEntry",
    "action_required",
    "classify_status",
    "normalise_text",
    "read_tracker",
    "read_tracker_statuses",
    "record_tracker_status",
    "strip_location_suffix",
    "tracker_row_matches",
]

from .status import (
    ACTION_REQUIRED,
    TRACKER_STATUSES,
    classify_tracker_status,
    normalise_text,
    strip_location_suffix,
    tracker_row_matches,
)

TRACKER_URL = "https://myjobs.indeed.com/applied"
STATUS_DATE = '[data-testid="jobStatusDateShort"]'
UPDATE_STATUS = 'button:has-text("Update status")'
MENU_SHEET = '[data-testid="actionSheetIFLMenu"]'
MENU_ITEM = '[data-testid="OverflowMenuItem"]'


_JS_ENTRIES = r"""() => {
  const dates = Array.from(document.querySelectorAll('[data-testid="jobStatusDateShort"]'));
  const out = [];
  for (const dateNode of dates) {
    let card = dateNode;
    for (let i = 0; i < 6 && card.parentElement; i++) {
      card = card.parentElement;
      if (card.querySelector('a[href*="viewjob"], a[aria-label*="job description"]')) break;
    }
    const lines = (card.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    out.push({ lines: lines.slice(0, 10) });
  }
  return out;
}"""


@dataclass(frozen=True, slots=True)
class TrackerEntry:
    """One application as Indeed records it."""

    title: str
    company: str
    location: str
    status: str
    status_text: str
    applied_on: str


def _is_boilerplate(line: str) -> bool:
    """True for Indeed's own filler text inside a card."""
    lowered = line.strip().lower()
    return "job description opens in a new window" in lowered or lowered == "older"


def _is_tab(line: str) -> bool:
    """True for the tracker tab labels that share the card container."""
    return line.strip() in {"Applied", "Saved", "Interviews", "Archived", "Last 14 days"}


def classify_status(text: str) -> str:
    """Map Indeed's status wording to our own status names.

    The date line Indeed renders under every card ("Applied on Indeed on
    Tuesday") is recognised as a DATE and never mistaken for the plain
    status "applied".
    """
    return classify_tracker_status(text)


def _is_applied_on(text: str) -> bool:
    """True for Indeed's "Applied on Indeed on <day>" date line."""
    lowered = (text or "").strip().casefold()
    return lowered.startswith("applied on indeed") or " on indeed on " in lowered


def tracker_row_matches_entry(record: dict, entry: TrackerEntry) -> bool:
    """Two-argument matcher kept for existing call sites; normalises both sides."""
    return tracker_row_matches(record, entry)


def open_tracker(page: Any) -> None:
    """Navigate to the application tracker."""
    page.goto(TRACKER_URL, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(3000)


def read_tracker(page: Any) -> list[TrackerEntry]:
    """Read every application row and its status."""
    try:
        raw = page.evaluate(_JS_ENTRIES)
    except Exception as error:
        raise IndeedScraperError(f"Could not read the application tracker: {error}") from error

    entries: list[TrackerEntry] = []
    for record in raw or []:
        lines = [str(line) for line in record.get("lines", [])]
        # Indeed renders each card as: status, title, company, location, date.
        lines = [
            line
            for line in lines
            if not _is_boilerplate(line) and not _is_tab(line)
        ]
        status_text = ""
        title = ""
        company = ""
        location = ""
        applied_on = ""
        rest: list[str] = []
        for line in lines:
            lowered = line.lower()
            if not status_text and classify_status(line) != "unknown":
                status_text = line
                continue
            if lowered.startswith("applied on indeed") or " on indeed on " in lowered:
                applied_on = applied_on or line
                continue
            rest.append(line)
        if rest:
            title = rest[0]
        if len(rest) > 1:
            company = rest[1]
        if len(rest) > 2:
            location = rest[2]
        entries.append(
            TrackerEntry(
                # The title and company are NORMALISED, and the location
                # suffix Indeed appends to a card title is removed. That is
                # what makes the mirror fire: the ledger stores the same
                # normalised form (apply/ledger.py reserve()), so the
                # comparison the CLI performs is between two equal strings
                # instead of two spellings of the same posting.
                title=normalise_text(strip_location_suffix(title)),
                company=normalise_text(company),
                location=location,
                status=classify_status(status_text),
                status_text=status_text,
                applied_on=applied_on,
            )
        )
    return entries


def action_required(entry: TrackerEntry) -> bool:
    """True when the operator must act on this application."""
    return entry.status in ACTION_REQUIRED


def available_statuses(page: Any) -> list[str]:
    """The status names Indeed offers in the \"Update status\" menu (read-only)."""
    try:
        buttons = page.locator(UPDATE_STATUS)
        if buttons.count() == 0:
            return []
        buttons.first.click()
        page.wait_for_timeout(1500)
        items = page.locator(f"{MENU_SHEET} {MENU_ITEM}")
        names = []
        for index in range(items.count()):
            text = (items.nth(index).inner_text() or "").strip()
            if text:
                names.append(text)
        return names
    except Exception:  # noqa: BLE001 - the menu is optional
        return []

#: The tracker status is kept in its OWN store, never in the application
#: ledger: the ledger's status is the idempotency guard ("submitted" means
#: submitted), and overwriting it with "hired" would let the flow apply to
#: the same posting a second time.
TRACKER_STATUS_FILENAME = "tracker_status.jsonl"


def tracker_status_path(state_dir: Path) -> Path:
    """Where the tracker statuses are kept (0600, append-only)."""
    return state_dir / "applications" / TRACKER_STATUS_FILENAME


def record_tracker_status(
    state_dir: Path,
    *,
    fingerprint: str,
    status: str,
    status_text: str = "",
    title: str = "",
    company: str = "",
) -> Path:
    """Record Indeed's status for one application, in the tracker store.

    The store is append-only, so we make it idempotent by skipping a write
    when the latest record for the fingerprint already has the same status.
    """
    path = tracker_status_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)

    # Idempotency check: if the latest entry for this fingerprint already
    # has the same status, do not append a duplicate.
    if path.is_file():
        try:
            latest_status = None
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("fingerprint") == fingerprint:
                    latest_status = rec.get("status")
                    break
            if latest_status == status:
                # Already recorded; nothing to do.
                return path
        except OSError:
            pass

    record = {
        "fingerprint": fingerprint,
        "status": status,
        "status_text": status_text,
        "title": title,
        "company": company,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return path


def read_tracker_statuses(state_dir: Path) -> list[dict]:
    """Read the tracker statuses, newest last, skipping malformed lines.

    Returns one record per fingerprint (the latest).
    """
    path = tracker_status_path(state_dir)
    if not path.is_file():
        return []
    seen: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            fp = str(payload.get("fingerprint", ""))
            if fp:
                # Overwrite with later entries; iteration is chronological.
                seen[fp] = payload
    return list(seen.values())
