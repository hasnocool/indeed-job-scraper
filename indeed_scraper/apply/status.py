"""The status vocabulary and the rule that matches a tracker row to an application.

Two jobs live here.

**The vocabulary.** Indeed shows a fixed set of statuses on the application
tracker. Each one has to be recognised, and each one has to mean the same
thing in the tracker store and in the response monitor - otherwise the
operator sees "unknown" for an offer and cannot tell an offer from a
rejection.

The old vocabulary had two traps:

* it was too small, so most real statuses fell through to "unknown";
* the matcher used a substring test, and the phrase "applied" is a substring
  of "Applied on Indeed on Tuesday" - so the DATE line of every card was
  consumed as the status.

**The match.** A tracker row and a ledger row describe the same posting, but
they never look identical: Indeed appends the location to the card title
("HVAC Technician - Calgary, AB") and punctuates the company differently
("Assure Home Assist, Inc." on the posting, "Assure Home Assist Inc" on the
card). An exact comparison therefore never fired, and the mirror count
stayed at zero for every run.

The rule here normalises BOTH sides and then requires:

* the companies to match, and
* the titles to match once the location suffix is removed.

Both halves are required, so a match can never cross companies. Two
postings that share a title AND a company remain AMBIGUOUS, and an ambiguous
match is skipped rather than guessed: attaching an offer to the wrong
application is worse than not recording it at all.

This module lives on its own so ``apply/tracker.py`` and
``response_monitor/indeed.py`` share ONE vocabulary and cannot drift apart.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

#: The statuses Indeed shows on the application tracker, mapped to our own
#: names. The order matters: the FIRST match wins, so the more specific
#: phrases come first.
TRACKER_STATUSES: dict[str, str] = {
    "offer received": "offer",
    "hired": "hired",
    "interviewing": "interview",
    "interview scheduled": "interview",
    "no longer interested": "not_interested",
    "not selected by employer": "not_selected",
    "application viewed": "viewed",
    "under review": "review",
    "job closed or expired on indeed": "closed",
    "applied": "applied",
}

#: The status names that mean the operator must act. An offer is never acted
#: on automatically - it is escalated.
ACTION_REQUIRED = frozenset({"offer", "hired"})

#: The statuses the response monitor reports. An offer and a hire are
#: reported under their own names so the operator can see them; they are
#: NOT folded into "interview", which would hide the one status that
#: matters most.
RESPONSE_STATUSES: tuple[str, ...] = (
    "applied",
    "viewed",
    "interview",
    "offer",
    "hired",
    "rejected",
    "withdrawn",
    "closed",
    "review",
    "unknown",
)

#: The tracker status names that map onto a response-monitor status.
_TRACKER_TO_RESPONSE: dict[str, str] = {
    "offer": "offer",
    "hired": "hired",
    "interview": "interview",
    "not_interested": "withdrawn",
    "not_selected": "rejected",
    "viewed": "viewed",
    "closed": "closed",
    "review": "review",
    "applied": "applied",
}

#: Indeed's own phrasing that carries a rejection.
_REJECTION_PHRASES = (
    "we have decided not to move forward",
    "not selected by employer",
    "not moving forward",
)

#: A card title that Indeed appends the location to:
#: "HVAC Technician (Refrigeration & Gas Techs) - Calgary, AB".
#: The suffix is removed before the titles are compared.
_LOCATION_SUFFIX = re.compile(
    r"\s+[-–—]\s+[^-–—]*$"
)

#: Punctuation and spacing that carry no meaning for a match.
_PUNCTUATION = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalise_text(value: str) -> str:
    """Normalise a title or a company for comparison.

    * NFKD-folded and casefolded, so "Assure Home Assist" and "assure home
      assist" are the same;
    * punctuation removed, so "Assure Home Assist, Inc." and "Assure Home
      Assist Inc" are the same;
    * whitespace collapsed.

    Nothing else is removed: the words themselves must still agree.
    """
    folded = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
    lowered = without_marks.casefold()
    stripped = _PUNCTUATION.sub(" ", lowered)
    return _WHITESPACE.sub(" ", stripped).strip()


def strip_location_suffix(title: str) -> str:
    """Remove the location Indeed appends to a card title.

    "HVAC Technician - Calgary, AB" -> "HVAC Technician".
    Only a trailing " - location" is removed, so a title that legitimately
    contains a dash ("Server-side Engineer - Remote") keeps its meaning.
    """
    cleaned = (title or "").strip()
    if " - " not in cleaned:
        return cleaned
    head, _, tail = cleaned.rpartition(" - ")
    if not head.strip():
        return cleaned
    # A location suffix has no digits-only content and is short; a job
    # description after a dash is usually longer. Keep the rule simple and
    # safe: only strip when the tail looks like a place.
    if _looks_like_location(tail):
        return head.strip()
    return cleaned


def _looks_like_location(tail: str) -> bool:
    """True when a trailing fragment looks like a location, not a job title."""
    candidate = tail.strip()
    if not candidate:
        return False
    # "Calgary, AB" / "Libertyville, IL 60048" / "Remote" / "Hybrid - BC"
    if "," in candidate or candidate.casefold() in {
        "remote",
        "hybrid",
        "on site",
        "onsite",
        "in person",
    }:
        return True
    # A bare province/state/country code.
    return bool(re.fullmatch(r"[A-Z]{2,3}(?:[ ,/-][A-Z0-9]{1,8})*", candidate))


def classify_tracker_status(text: str) -> str:
    """Map Indeed's status wording to our own status names.

    The phrase list is ordered so the most specific phrase wins.

    The DATE line Indeed renders under every card ("Applied on Indeed on
    Tuesday") is a special case: it contains the word "applied", but it is a
    date, not a status. It still classifies as "applied" - the application
    WAS applied - but the caller that parses a card uses ``is_applied_on``
    to tell the date line apart from the status line.
    """
    lowered = (text or "").strip().casefold()
    if not lowered:
        return "unknown"
    for phrase, name in TRACKER_STATUSES.items():
        if phrase in lowered:
            return name
    return "unknown"


def is_applied_on(text: str) -> bool:
    """True for Indeed's "Applied on Indeed on <day>" date line."""
    lowered = (text or "").strip().casefold()
    return lowered.startswith("applied on indeed") or " on indeed on " in lowered


def response_status_for(text: str) -> str:
    """Map a status text to a response-monitor status.

    The real Indeed vocabulary is understood, and an OFFER keeps its own
    name: folding it into "interview" would hide the one status the
    operator must act on.
    """
    lowered = (text or "").strip().casefold()
    if not lowered:
        return "unknown"
    for phrase in _REJECTION_PHRASES:
        if phrase in lowered:
            return "rejected"
    tracker = classify_tracker_status(lowered)
    if tracker != "unknown":
        return _TRACKER_TO_RESPONSE.get(tracker, tracker)
    return "unknown"


def tracker_row_matches(record: dict, entry: Any) -> bool:
    """True when a ledger record is the SAME posting as a tracker entry.

    Both sides are normalised, and the location suffix Indeed appends to a
    card title is removed from the tracker title.

    The company MUST match. That is what keeps the match from crossing
    applications: a title alone is not unique (one company posts the same
    title in several cities), but a title plus a company is, and when even
    that is ambiguous the caller skips the row rather than guessing.
    """
    record_title = str(record.get("title", "")).strip()
    record_company = str(record.get("company", "")).strip()
    if not record_title or not record_company:
        return False

    title = str(getattr(entry, "title", "") or "").strip()
    company = str(getattr(entry, "company", "") or "").strip()
    if not title or not company:
        return False

    if normalise_text(record_company) != normalise_text(company):
        return False

    record_title_norm = normalise_text(strip_location_suffix(record_title))
    tracker_title_norm = normalise_text(strip_location_suffix(title))
    if not record_title_norm or not tracker_title_norm:
        return False
    return record_title_norm == tracker_title_norm
