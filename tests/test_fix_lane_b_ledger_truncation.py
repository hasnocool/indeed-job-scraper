"""B3 - a truncated final ledger line must not silently un-reserve a posting.

The ledger is append-only JSONL. A crash in the middle of an append can leave
a PARTIAL last line: no trailing newline, and the JSON is cut off.

The old parser skipped every malformed line, so a truncated reservation was
dropped entirely: the posting became invisible to the idempotency guard and
could be applied to a SECOND time.

The rule this file pins:

* a truncated FINAL line is a reservation that may or may not have been
  written - it is treated as LIVE (blocked), because a duplicate application
  is worse than a missed one;
* a malformed line in the MIDDLE is skipped, but it is SURFACED, not
  silently vanished.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indeed_scraper.apply.ledger import ApplicationLedger


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_truncated_final_reservation_blocks_the_posting(tmp_path: Path) -> None:
    """A torn final line must keep the posting blocked.

    The reservation may have been written before the crash; if we ignore the
    partial line we allow the posting to be applied to twice.
    """
    path = tmp_path / "ledger.jsonl"
    good = (
        '{"fingerprint":"fp-1","jk":"jk1","indeed_url":"u","status":"reserved",'
        '"detail":"","applied_at":"2026-01-01T00:00:00+00:00"}\n'
    )
    # A reservation whose line was cut off mid-write by the crash.
    torn = '{"fingerprint":"fp-torn","jk":"jk2","indeed_url":"u","status":"rese'
    _write(path, good + torn)

    ledger = ApplicationLedger(path)

    assert ledger.status_of("fp-torn") is not None, (
        "a truncated final reservation must not vanish: the posting would "
        "look untouched and could be applied to twice"
    )
    assert ledger.reserve("fp-torn", "jk2", "u") is False, (
        "a posting whose reservation was torn by a crash must not be "
        "reservable again"
    )


def test_a_truncated_final_submission_blocks_the_posting(tmp_path: Path) -> None:
    """The same rule for a torn 'submitting' line: it is the worst case."""
    path = tmp_path / "ledger.jsonl"
    torn = '{"fingerprint":"fp-torn","jk":"jk2","status":"submitt'
    _write(path, torn)

    ledger = ApplicationLedger(path)

    assert ledger.reserve("fp-torn", "jk2", "u") is False


def test_a_truncated_final_line_does_not_block_other_postings(tmp_path: Path) -> None:
    """One torn line must not lock the whole ledger."""
    path = tmp_path / "ledger.jsonl"
    _write(
        path,
        '{"fingerprint":"fp-1","jk":"jk1","status":"reserved","detail":"",'
        '"applied_at":"2026-01-01T00:00:00+00:00"}\n'
        '{"fingerprint":"fp-torn","jk":"jk2","status":"rese',
    )

    ledger = ApplicationLedger(path)

    assert ledger.reserve("fp-2", "jk3", "u") is True
    assert ledger.status_of("fp-1") == "reserved"


def test_a_malformed_line_in_the_middle_is_surfaced_not_vanished(
    tmp_path: Path,
) -> None:
    """A malformed middle line is skipped, but the operator is told.

    Silently dropping a corrupted line hides a real problem with the file.
    """
    path = tmp_path / "ledger.jsonl"
    _write(
        path,
        '{"fingerprint":"fp-1","jk":"jk1","status":"reserved","detail":"",'
        '"applied_at":"2026-01-01T00:00:00+00:00"}\n'
        "this line is not json at all\n"
        '{"fingerprint":"fp-2","jk":"jk2","status":"submitted","detail":"",'
        '"applied_at":"2026-01-01T00:00:00+00:00"}\n',
    )

    with pytest.warns(RuntimeWarning, match="malformed"):
        ledger = ApplicationLedger(path)

    assert ledger.status_of("fp-1") == "reserved"
    assert ledger.status_of("fp-2") == "submitted"


def test_a_clean_ledger_warns_about_nothing(tmp_path: Path) -> None:
    """A healthy ledger must be silent."""
    path = tmp_path / "ledger.jsonl"
    _write(
        path,
        '{"fingerprint":"fp-1","jk":"jk1","status":"reserved","detail":"",'
        '"applied_at":"2026-01-01T00:00:00+00:00"}\n',
    )

    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ApplicationLedger(path)

    assert [w for w in caught if issubclass(w.category, RuntimeWarning)] == []


def test_the_torn_reservation_is_released_by_the_lease(tmp_path: Path) -> None:
    """A torn reservation must still be releasable once it is stale.

    Blocking for ever would be as bad as never blocking: the lease has to
    work on the recovered reservation too.
    """
    from datetime import datetime, timedelta, timezone

    path = tmp_path / "ledger.jsonl"
    old = datetime.now(tz=timezone.utc) - timedelta(hours=3)
    # A torn line that still carries its timestamp.
    torn = (
        '{"fingerprint":"fp-torn","jk":"jk2","status":"reserved",'
        f'"applied_at":"{old.isoformat()}","detail":"'
    )
    _write(path, torn)

    ledger = ApplicationLedger(path)

    age = ledger.reservation_age("fp-torn")
    assert age is not None, "a torn reservation must still expose its age"
    assert age > 2 * 60 * 60
