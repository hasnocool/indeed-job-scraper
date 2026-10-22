"""The ledger's status vocabulary, in ONE place.

Every component that reads the application ledger has to agree on what a
status MEANS. Wave 1 introduced ``unconfirmed`` - a submit click that was
dispatched but whose confirmation could not be read - and updated most of
the readers. The response monitor was missed, and it kept filtering on the
literal string ``"submitted"``, so an application that may have reached a
real employer simply did not appear in the operator's status report.

That class of bug is a vocabulary bug: the same concept spelled out in
several places, with each copy free to drift. This module holds the
vocabulary so there is exactly ONE definition of "which ledger statuses
count as an application that went out".

Two vocabularies live here, and they are NOT the same thing:

``LEDGER_STATUSES``
    the statuses the ledger writes.

``SUBMITTED_LIKE_STATUSES``
    the statuses that mean "an application may have reached the employer".
    This is what a status REPORT has to show: an application the operator
    might have to chase.

Keeping them apart matters. ``"submitting"`` is a ledger status but not a
submitted-like one: it means the click was ABOUT to happen, and an
application stuck in that state has usually NOT gone out. Showing it as an
application would be as misleading as hiding a real one.
"""

from __future__ import annotations

__all__ = [
    "LEDGER_STATUSES",
    "SUBMITTED_LIKE_STATUSES",
    "is_submitted_like",
]

#: Every status the application ledger writes. Kept here so a component
#: that has to recognise one cannot invent a spelling of its own.
LEDGER_STATUSES: frozenset[str] = frozenset(
    {
        "reserved",
        "submitting",
        "submitted",
        "unconfirmed",
        "blocked",
        "failed",
        "dry_run",
        "skipped",
    }
)

#: The statuses that mean "an application may have reached the employer".
#:
#: * ``submitted`` - a real confirmation signal was observed.
#: * ``unconfirmed`` - the click was dispatched and the confirmation could
#:   not be read. It may already have reached the employer.
#:
#: A status REPORT must show both. Hiding the unconfirmed one hides an
#: application the operator may need to chase, and the whole point of
#: recording the uncertainty is to act on it.
SUBMITTED_LIKE_STATUSES: frozenset[str] = frozenset({"submitted", "unconfirmed"})


def is_submitted_like(status: str | None) -> bool:
    """True when a ledger status means "an application may have gone out"."""
    return status in SUBMITTED_LIKE_STATUSES
