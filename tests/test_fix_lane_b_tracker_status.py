"""B4 + B5 - the tracker status vocabulary and the mirror that never fired.

Two defects, both of which made `sync` and `check-responses` useless:

**B4 - the tracker mirror never mirrors anything.** The match demanded an
exact title AND an exact company. Real Indeed rows never satisfy that: the
card title carries the location ("Veteran Community Relations & Business
Development Specialist - Libertyville, IL 60048") and the company is
punctuated differently ("Assure Home Assist Inc" vs "Assure Home Assist,
Inc."). So every row was skipped and the mirror count stayed at zero.

**B5 - every real Indeed status classified as `unknown`.** The vocabulary
was too small, and the matcher had a trap: the phrase "applied" is a
substring of "Applied on Indeed on Tuesday", so the DATE line was consumed
as the status and every card came out as "applied".

The rule this file pins:

* the real Indeed status vocabulary is recognised, and the date line is
  never mistaken for a status;
* the match actually fires on a realistic row, and it CANNOT mis-attach:
  an ambiguous match is still skipped, never guessed;
* the tracker status is NEVER written into the application ledger - the
  ledger's status is the idempotency guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.tracker import (
    ACTION_REQUIRED,
    TRACKER_STATUSES,
    TrackerEntry,
    action_required,
    classify_status,
    read_tracker,
    read_tracker_statuses,
    record_tracker_status,
)

# --------------------------------------------------------------------------
# A realistic Indeed tracker card, as the page renders it.
# --------------------------------------------------------------------------

REAL_CARD_LINES = [
    "Not selected by employer",
    "Veteran Community Relations & Business Development Specialist - Libertyville, IL 60048",
    "Assure Home Assist Inc",
    "Libertyville, IL 60048",
    "Applied on Indeed on Tuesday",
]


class _FakePage:
    """A page double that returns one tracker card."""

    def __init__(self, cards: list[list[str]]) -> None:
        self._cards = cards

    def evaluate(self, script: str) -> list[dict]:
        return [{"lines": list(lines)} for lines in self._cards]


# --------------------------------------------------------------------------
# B5 - the status vocabulary
# --------------------------------------------------------------------------


def test_the_real_indeed_statuses_are_recognised() -> None:
    """Every status Indeed actually shows must map to a known name."""
    for text, expected in (
        ("Offer received", "offer"),
        ("Hired", "hired"),
        ("Interviewing", "interview"),
        ("Interview scheduled", "interview"),
        ("No longer interested", "not_interested"),
        ("Not selected by employer", "not_selected"),
        ("Application viewed", "viewed"),
        ("Job closed or expired on Indeed", "closed"),
        ("Applied", "applied"),
        ("Under review", "review"),
        ("Applied on Indeed on Tuesday", "applied"),
    ):
        assert classify_status(text) == expected, text


def test_an_offer_is_still_escalated_not_acted_on() -> None:
    """The vocabulary may grow, but an offer must stay action-required."""
    assert classify_status("Offer received") == "offer"
    assert "offer" in ACTION_REQUIRED
    assert action_required(TrackerEntry("R", "C", "L", "offer", "Offer received", "")) is True


def test_an_unknown_status_is_still_unknown() -> None:
    """The vocabulary must not become a catch-all."""
    assert classify_status("Something else entirely") == "unknown"
    assert classify_status("") == "unknown"


def test_the_date_line_is_not_mistaken_for_a_status() -> None:
    """'Applied on Indeed on Tuesday' is a date, not a status."""
    status = classify_status("Applied on Indeed on Tuesday")
    assert status == "applied"
    # But the DATE must still be recognisable as a date.
    from indeed_scraper.apply.tracker import _is_applied_on

    assert _is_applied_on("Applied on Indeed on Tuesday") is True


# --------------------------------------------------------------------------
# B4 - reading a realistic card
# --------------------------------------------------------------------------


def test_a_realistic_tracker_card_yields_its_status_and_title() -> None:
    """The status line must be found, and the date must not swallow it.

    The title and company are NORMALISED (and the location suffix Indeed
    appends is removed): that is what makes the mirror fire, because the
    ledger stores the same normalised form.
    """
    from indeed_scraper.apply.status import normalise_text, strip_location_suffix

    entries = read_tracker(_FakePage([REAL_CARD_LINES]))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.status == "not_selected"
    assert entry.status_text == "Not selected by employer"
    assert entry.title == normalise_text(
        strip_location_suffix(
            "Veteran Community Relations & Business Development Specialist"
        )
    )
    assert entry.company == normalise_text("Assure Home Assist Inc")


def test_a_tracker_card_with_an_offer_is_recognised() -> None:
    """The most important status of all must survive the parsing."""
    lines = [
        "Offer received",
        "HVAC Technician (Refrigeration & Gas Techs) - Calgary, AB",
        "Abundant Air Inc.",
        "Calgary, AB",
        "Applied on Indeed on Monday",
    ]
    entries = read_tracker(_FakePage([lines]))

    assert entries[0].status == "offer"
    assert entries[0].status_text == "Offer received"


# --------------------------------------------------------------------------
# B4 - the match that actually fires
# --------------------------------------------------------------------------


def _normalise(value: str) -> str:
    """The shared normalisation the match is built on."""
    from indeed_scraper.apply.tracker import normalise_text

    return normalise_text(value)


def test_a_title_with_a_location_suffix_matches_the_ledger_title() -> None:
    """Indeed appends the location to the card title; it must still match."""
    from indeed_scraper.apply.tracker import tracker_row_matches

    record = {
        "title": "Veteran Community Relations & Business Development Specialist",
        "company": "Assure Home Assist, Inc.",
    }
    entry = TrackerEntry(
        title="Veteran Community Relations & Business Development Specialist - Libertyville, IL 60048",
        company="Assure Home Assist Inc",
        location="Libertyville, IL 60048",
        status="not_selected",
        status_text="Not selected by employer",
        applied_on="Applied on Indeed on Tuesday",
    )
    assert tracker_row_matches(record, entry) is True


def test_a_company_with_different_punctuation_matches() -> None:
    """"Assure Home Assist, Inc." and "Assure Home Assist Inc" are one company."""
    from indeed_scraper.apply.tracker import tracker_row_matches

    record = {"title": "HVAC Technician (Refrigeration & Gas Techs)", "company": "Abundant Air Inc."}
    entry = TrackerEntry(
        title="HVAC Technician (Refrigeration & Gas Techs) - Calgary, AB",
        company="Abundant Air Inc",
        location="Calgary, AB",
        status="interview",
        status_text="Interviewing",
        applied_on="",
    )
    assert tracker_row_matches(record, entry) is True


def test_a_different_company_never_matches() -> None:
    """A wrong company must never match - that would mis-attach a status."""
    from indeed_scraper.apply.tracker import tracker_row_matches

    record = {"title": "Data Engineer", "company": "Acme"}
    entry = TrackerEntry(
        title="Data Engineer - Remote",
        company="Globex",
        location="Remote",
        status="offer",
        status_text="Offer received",
        applied_on="",
    )
    assert tracker_row_matches(record, entry) is False


def test_an_empty_title_or_company_never_matches() -> None:
    """An incomplete record must not match anything."""
    from indeed_scraper.apply.tracker import tracker_row_matches

    entry = TrackerEntry("Data Engineer", "Acme", "Remote", "offer", "Offer received", "")
    assert tracker_row_matches({"title": "", "company": "Acme"}, entry) is False
    assert tracker_row_matches({"title": "Data Engineer", "company": ""}, entry) is False


# --------------------------------------------------------------------------
# The mirror, end to end
# --------------------------------------------------------------------------


def test_a_realistic_tracker_row_mirrors_onto_the_application(
    tmp_path: Path,
) -> None:
    """A realistic tracker row MUST mirror - that is the whole point of B4."""
    from indeed_scraper.cli import _mirror_tracker_statuses

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve(
        "fp-1",
        "jk-1",
        "https://ca.indeed.com/viewjob?jk=jk-1",
        company="Assure Home Assist, Inc.",
        title="Veteran Community Relations & Business Development Specialist",
    )
    ledger.mark("fp-1", "submitted", "")

    entries = read_tracker(_FakePage([REAL_CARD_LINES]))

    mirrored = _mirror_tracker_statuses(ledger, entries, tmp_path)

    assert mirrored == 1, (
        "a realistic tracker row must mirror; the old exact-match rule "
        f"skipped every row (mirrored {mirrored})"
    )
    statuses = read_tracker_statuses(tmp_path)
    assert len(statuses) == 1
    assert statuses[0]["fingerprint"] == "fp-1"
    assert statuses[0]["status"] == "not_selected"


def test_an_ambiguous_match_is_skipped_not_guessed(tmp_path: Path) -> None:
    """Two postings with the same title and company -> no mirror.

    Attaching a status to the wrong application is worse than not writing
    it, so an ambiguous match stays unmatched.
    """
    from indeed_scraper.cli import _mirror_tracker_statuses

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    for fp in ("fp-1", "fp-2"):
        ledger.reserve(
            fp,
            f"jk-{fp}",
            "u",
            company="Acme",
            title="Data Engineer",
        )
        ledger.mark(fp, "submitted", "")

    entry = TrackerEntry(
        title="Data Engineer - Remote",
        company="Acme",
        location="Remote",
        status="offer",
        status_text="Offer received",
        applied_on="",
    )

    mirrored = _mirror_tracker_statuses(ledger, [entry], tmp_path)

    assert mirrored == 0
    assert read_tracker_statuses(tmp_path) == []


def test_the_tracker_status_is_never_written_into_the_ledger(
    tmp_path: Path,
) -> None:
    """THE INVARIANT: the ledger's status is the idempotency guard.

    Overwriting "submitted" with "hired" would let the flow apply to the
    same posting a second time.
    """
    from indeed_scraper.cli import _mirror_tracker_statuses

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve(
        "fp-1",
        "jk-1",
        "u",
        company="Acme",
        title="Data Engineer",
    )
    ledger.mark("fp-1", "submitted", "")

    entry = TrackerEntry(
        title="Data Engineer - Remote",
        company="Acme",
        location="Remote",
        status="hired",
        status_text="Hired",
        applied_on="",
    )

    _mirror_tracker_statuses(ledger, [entry], tmp_path)

    assert ledger.status_of("fp-1") == "submitted", (
        "the tracker status must never overwrite the ledger's status"
    )
    ledger_text = ledger.path.read_text(encoding="utf-8")
    assert "hired" not in ledger_text


def test_the_tracker_store_is_separate_from_the_ledger(tmp_path: Path) -> None:
    """The mirror writes to its OWN store."""
    record_tracker_status(
        tmp_path,
        fingerprint="fp-1",
        status="offer",
        status_text="Offer received",
        title="Data Engineer",
        company="Acme",
    )

    tracker_file = tmp_path / "applications" / "tracker_status.jsonl"
    assert tracker_file.is_file()
    records = [json.loads(line) for line in tracker_file.read_text(encoding="utf-8").splitlines()]
    assert records[0]["status"] == "offer"
    assert not (tmp_path / "applications" / "ledger.jsonl").exists()


def test_the_tracker_store_is_0600(tmp_path: Path) -> None:
    """The tracker store holds application outcomes; it must be private."""
    record_tracker_status(tmp_path, fingerprint="fp-1", status="offer")
    path = tmp_path / "applications" / "tracker_status.jsonl"
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_the_tracker_vocabulary_covers_the_real_statuses() -> None:
    """The vocabulary must keep every status Indeed shows."""
    for phrase in (
        "offer received",
        "hired",
        "interviewing",
        "no longer interested",
        "not selected by employer",
        "application viewed",
        "job closed or expired on indeed",
        "applied",
    ):
        assert phrase in TRACKER_STATUSES, phrase


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Offer received", "offer"),
        ("Hired", "hired"),
        ("Interviewing", "interview"),
        ("No longer interested", "withdrawn"),
        ("Not selected by employer", "rejected"),
        ("Application viewed", "viewed"),
        ("Job closed or expired on Indeed", "closed"),
        ("Applied", "applied"),
        ("We have decided not to move forward", "rejected"),
        ("", "unknown"),
        ("Something else entirely", "unknown"),
    ],
)
def test_the_response_monitor_knows_the_real_statuses(text: str, expected: str) -> None:
    """B5: `check-responses` must understand the real vocabulary.

    The response monitor has its OWN vocabulary: a rejection and a
    withdrawal are what the operator cares about, and they are the same
    thing to them whatever Indeed calls it. An OFFER keeps its own name -
    folding it into "interview" would hide the one status that must be
    acted on.
    """
    from indeed_scraper.response_monitor.indeed import parse_status

    assert parse_status(text) == expected, text
