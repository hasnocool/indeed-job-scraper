"""Regression tests for the application flow's guard rails.

These cover the rules that must hold when a posting is attempted: a dry run
must not consume the posting, and a failure after the reservation must never
leave an unexplained reservation behind.
"""

from __future__ import annotations

from pathlib import Path

from indeed_scraper.apply.ledger import ApplicationLedger


def test_dry_run_releases_the_reservation(tmp_path: Path) -> None:
    """A rehearsal must leave the posting applyable for a later real run.

    The reservation exists to stop a double SUBMIT. A dry run submits
    nothing, so it must release the reservation instead of blocking the
    posting forever.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fingerprint = "fp-dry-run"

    assert ledger.reserve(fingerprint=fingerprint, jk="jk1", indeed_url="u") is True
    assert ledger.status_of(fingerprint) == "reserved"

    # What the worker's dry-run branch does.
    ledger.mark(fingerprint, "failed", "dry_run")

    assert ledger.status_of(fingerprint) == "failed"
    assert ledger.status_of(fingerprint) not in {"reserved", "submitted"}


def test_a_failed_attempt_never_leaves_a_dangling_reservation(tmp_path: Path) -> None:
    """Whatever happens after the reserve, the ledger records the outcome."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fingerprint = "fp-failed"

    ledger.reserve(fingerprint=fingerprint, jk="jk1", indeed_url="u")
    ledger.mark(fingerprint, "failed", "error:TimeoutError")

    assert ledger.status_of(fingerprint) == "failed"
    entries = [e for e in ledger.entries if e.get("fingerprint") == fingerprint]
    assert entries[-1]["detail"] == "error:TimeoutError"


def test_a_submitted_posting_stays_blocked(tmp_path: Path) -> None:
    """A real submission must keep the posting blocked for good."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fingerprint = "fp-submitted"

    ledger.reserve(fingerprint=fingerprint, jk="jk1", indeed_url="u")
    ledger.mark(fingerprint, "submitted", "")

    assert ledger.status_of(fingerprint) == "submitted"
    assert ledger.status_of(fingerprint) in {"reserved", "submitted"}
    assert ledger.has(fingerprint) is True
    # A second attempt at the same posting is refused.
    assert ledger.reserve(fingerprint=fingerprint, jk="jk1", indeed_url="u") is False
