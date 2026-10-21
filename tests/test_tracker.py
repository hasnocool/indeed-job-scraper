"""Tests for reading Indeed's application tracker.

The tracker is where Indeed records what happened to an application, so the
status vocabulary and the escalation rule matter: an offer must be surfaced to
the operator, never acted on.
"""

from __future__ import annotations

from indeed_scraper.apply.tracker import (
    ACTION_REQUIRED,
    TrackerEntry,
    action_required,
    classify_status,
)


def test_an_offer_is_recognised() -> None:
    assert classify_status("Offer received") == "offer"


def test_hired_and_interviewing_are_recognised() -> None:
    assert classify_status("Hired") == "hired"
    assert classify_status("Interviewing") == "interview"


def test_the_employers_own_outcomes_are_recognised() -> None:
    assert classify_status("Not selected by employer") == "not_selected"
    assert classify_status("Job closed or expired on Indeed") == "closed"
    assert classify_status("No longer interested") == "not_interested"
    assert classify_status("Applied on Indeed on Tuesday") == "applied"
    assert classify_status("Application viewed") == "viewed"


def test_an_unknown_status_is_unknown() -> None:
    assert classify_status("Something else entirely") == "unknown"
    assert classify_status("") == "unknown"


def test_an_offer_requires_the_operator() -> None:
    """An offer is escalated, never acted on automatically."""
    offer = TrackerEntry("Role", "Acme", "BC", "offer", "Offer received", "Applied on Indeed")
    assert action_required(offer) is True
    assert "offer" in ACTION_REQUIRED


def test_a_hired_application_also_requires_the_operator() -> None:
    hired = TrackerEntry("Role", "Acme", "BC", "hired", "Hired", "Applied on Indeed")
    assert action_required(hired) is True


def test_an_ordinary_application_does_not_require_action() -> None:
    for status in ("applied", "viewed", "not_selected", "closed", "unknown"):
        entry = TrackerEntry("Role", "Acme", "BC", status, status, "Applied on Indeed")
        assert action_required(entry) is False, status
