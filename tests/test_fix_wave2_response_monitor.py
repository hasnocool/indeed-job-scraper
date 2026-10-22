"""Wave 2 — the response monitor must not hide an unconfirmed application.

**N1 MAJOR.** ``response_monitor/indeed.py`` filtered on the literal string
``"submitted"``, so an application whose submit click was dispatched but
whose confirmation could not be read - the NORMAL outcome on a real Indeed
form - never appeared in the operator's status report.

The operator's own report is where a half-sent application has to surface:
it may already have reached a real employer, and the operator is the only
one who can check.

An unconfirmed application must be:

* VISIBLE - it appears in the report at all;
* DISTINGUISHABLE from a confirmed submission - the operator must be able
  to tell "the employer confirmed it" from "we never found out";
* HONEST - it must not claim the employer received it.
"""

from __future__ import annotations

import json
from pathlib import Path

from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.response_monitor.indeed import collect_responses


def _ledger_with(tmp_path: Path, statuses: list[tuple[str, str]]) -> Path:
    """A ledger holding one entry per (fingerprint, status) pair."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    for fingerprint, status in statuses:
        ledger.reserve(fingerprint, f"jk-{fingerprint}", "https://ca.indeed.com/viewjob")
        if status != "reserved":
            ledger.mark(fingerprint, status, "")
    return ledger.path


def test_an_unconfirmed_application_is_not_hidden(tmp_path: Path) -> None:
    """The monitor must surface an unconfirmed application.

    Before the fix the monitor kept only the entries whose status was
    literally "submitted", so this produced ZERO records and the operator
    never learned that an application might have gone out.
    """
    ledger_path = _ledger_with(
        tmp_path,
        [("fp-unconf", "unconfirmed"), ("fp-conf", "submitted")],
    )

    records = collect_responses(ledger_path, tmp_path / "responses")

    assert len(records) == 2, (
        f"the monitor hid an application: {records!r}"
    )
    by_fp = {record["fingerprint"]: record for record in records}
    assert "fp-unconf" in by_fp, f"the unconfirmed application is missing: {records!r}"
    assert "fp-conf" in by_fp


def test_an_unconfirmed_application_is_distinguishable_from_a_confirmed_one(
    tmp_path: Path,
) -> None:
    """The report must say WHICH of the two it is.

    The operator has to be able to tell "the employer confirmed this" from
    "we never found out". A single status name for both would force the
    operator to check Indeed by hand for every application.
    """
    ledger_path = _ledger_with(
        tmp_path,
        [("fp-unconf", "unconfirmed"), ("fp-conf", "submitted")],
    )

    records = collect_responses(ledger_path, tmp_path / "responses")

    by_fp = {record["fingerprint"]: record for record in records}
    assert by_fp["fp-unconf"]["status"] != by_fp["fp-conf"]["status"], (
        "an unconfirmed application must be distinguishable from a confirmed one"
    )


def test_an_unconfirmed_application_does_not_claim_the_employer_received_it(
    tmp_path: Path,
) -> None:
    """The record must not assert that the employer got the application.

    The whole point of "unconfirmed" is that we do NOT know. A record that
    says "applied" would be a lie in the one place the operator reads.
    """
    ledger_path = _ledger_with(tmp_path, [("fp-unconf", "unconfirmed")])

    records = collect_responses(ledger_path, tmp_path / "responses")

    assert len(records) == 1
    record = records[0]
    assert record["status"] not in {"applied", "viewed", "interview", "offer", "hired"}, (
        f"an unconfirmed application must not claim the employer received it: {record!r}"
    )


def test_a_posting_that_never_was_submitted_is_still_hidden(tmp_path: Path) -> None:
    """The fix must not turn the report into a list of every reservation.

    A reserved, failed or blocked posting is not an application, and showing
    it would bury the real ones.
    """
    ledger_path = _ledger_with(
        tmp_path,
        [
            ("fp-reserved", "reserved"),
            ("fp-failed", "failed"),
            ("fp-blocked", "blocked"),
        ],
    )

    records = collect_responses(ledger_path, tmp_path / "responses")

    assert records == [], f"the report must only show applications that may have gone out: {records!r}"


def test_the_report_survives_a_mix_of_statuses(tmp_path: Path) -> None:
    """One of each status produces exactly the two application records."""
    ledger_path = _ledger_with(
        tmp_path,
        [
            ("fp-reserved", "reserved"),
            ("fp-submitting", "submitting"),
            ("fp-conf", "submitted"),
            ("fp-unconf", "unconfirmed"),
            ("fp-failed", "failed"),
        ],
    )

    records = collect_responses(ledger_path, tmp_path / "responses")

    assert {record["fingerprint"] for record in records} == {"fp-conf", "fp-unconf"}


def test_the_record_is_written_to_disk(tmp_path: Path) -> None:
    """The unconfirmed application is persisted, not just returned."""
    ledger_path = _ledger_with(tmp_path, [("fp-unconf", "unconfirmed")])
    responses_root = tmp_path / "responses"

    records = collect_responses(ledger_path, responses_root)

    app_id = records[0]["app_id"]
    written = responses_root / f"{app_id}.json"
    assert written.is_file(), f"the record was not written: {written}"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["fingerprint"] == "fp-unconf"
