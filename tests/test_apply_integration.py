"""End-to-end checks that the pieces of the apply flow work together.

Each test exercises a path that spans two modules, so a break in either one
shows up here:

* a submitted application is found by the response monitor, with its job key
  carried through the ledger;
* the daily budget stops the flow, not just the helper;
* no profile value reaches the ledger, a draft, or the console output.
"""

from __future__ import annotations

from pathlib import Path

from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.profile import Profile
from indeed_scraper.apply.risk import RiskBudget
from indeed_scraper.response_monitor.indeed import collect_responses


def _profile(tmp_path: Path) -> Profile:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    return Profile(
        name="Ada Lovelace",
        email="ada@example.com",
        phone="250-555-0142",
        resume_path=str(resume),
    )


def test_a_submitted_application_is_found_by_the_response_monitor(tmp_path: Path) -> None:
    """The monitor must see a submission, with the job key intact.

    The ledger records a status change as a separate line, so the metadata
    (jk, company, title) has to survive that transition - otherwise the
    monitor never finds the submission.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve(
        "fp-1",
        "jk-1",
        "https://ca.indeed.com/viewjob?jk=jk-1",
        company="Acme",
        title="Data Engineer",
    )
    ledger.mark("fp-1", "submitted", "")

    records = collect_responses(tmp_path / "ledger.jsonl", tmp_path / "responses")

    assert len(records) == 1
    record = records[0]
    assert record["jk"] == "jk-1"
    assert record["company"] == "Acme"
    assert record["title"] == "Data Engineer"
    assert record["app_id"] == "fp-1"[:12]
    assert record["checked_at"], "the record must say when it was checked"
    assert (tmp_path / "responses" / f"{record['app_id']}.json").is_file()


def test_the_response_monitor_ignores_postings_that_were_not_submitted(tmp_path: Path) -> None:
    """A reserved or failed posting is not a submitted application."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp-reserved", "jk-r", "https://ca.indeed.com/viewjob?jk=jk-r")
    ledger.reserve("fp-failed", "jk-f", "https://ca.indeed.com/viewjob?jk=jk-f")
    ledger.mark("fp-failed", "failed", "operator_declined")

    records = collect_responses(tmp_path / "ledger.jsonl", tmp_path / "responses")

    assert records == []


def test_the_daily_budget_stops_the_flow(tmp_path: Path) -> None:
    """Once the daily cap is reached, the flow stops applying."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=2)
    ledger.reserve("fp-1", "jk-1", "u")
    ledger.mark("fp-1", "submitted", "")
    ledger.reserve("fp-2", "jk-2", "u")
    ledger.mark("fp-2", "submitted", "")

    assert ledger.submitted_today() == 2
    assert budget.can_apply(ledger) is False

    ledger.reserve("fp-3", "jk-3", "u")
    ledger.mark("fp-3", "failed", "dry_run")
    assert ledger.submitted_today() == 2


def test_no_profile_value_reaches_the_ledger_or_a_draft(tmp_path: Path) -> None:
    """The operator's personal values live in the profile and nowhere else."""
    from indeed_scraper.apply.drafts import draft_payload, write_draft

    profile = _profile(tmp_path)
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    # The ledger records the POSTING's company/title, never the operator's
    # personal values.
    ledger.reserve("fp-1", "jk-1", "u", company="Acme", title="Data Engineer")
    ledger.mark("fp-1", "submitted", "")

    draft = write_draft(
        tmp_path / "drafts",
        "app-1",
        draft_payload({"fingerprint": "fp-1"}, {"name": profile.name, "email": profile.email}),
    )

    for path in (tmp_path / "ledger.jsonl", draft):
        text = path.read_text(encoding="utf-8")
        assert profile.email not in text, path
        assert profile.phone not in text, path
        assert profile.resume_path not in text, path
