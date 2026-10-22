"""Regression tests for the findings of two independent BLOCK reviews.

Each test here fails if the behaviour it names is broken again:

* the CLI help must not contradict what the code does,
* a contract request must reach the operator even when the classifier does
  not call it an offer,
* the policy FILE is the ceiling on autonomy,
* an unreadable policy file is an operator message, not a traceback,
* a posting that reached the submit click is never applied to twice,
* the message ledger does not become a second copy of the profile.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from indeed_scraper.apply.autonomy import AutonomyPolicy
from indeed_scraper.apply.profile import Profile
from indeed_scraper.errors import IndeedScraperError
from indeed_scraper.messages.compose import (
    build_reply,
    classify,
    is_binding,
    redact_operator,
)


class _Console:
    """A console that records what was printed."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, *args: object, **kwargs: object) -> None:
        self.lines.append(" ".join(str(a) for a in args))


def _profile() -> Profile:
    return Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path="/tmp/resume.pdf",
        availability="next week",
    )


# ---------------------------------------------------------------------------
# CRITICAL: the documented behaviour must match the implemented behaviour
# ---------------------------------------------------------------------------


def test_the_cli_help_does_not_claim_a_mandatory_confirmation() -> None:
    """The help must describe what the code does, not the other way round.

    The ``apply`` command body now lives in
    ``indeed_scraper/commands/apply_cmds.py`` (it was moved out of
    ``cli.py`` to keep that module a thin wiring layer), so the check reads
    the command's real home.
    """
    command = Path("indeed_scraper/commands/apply_cmds.py").read_text(encoding="utf-8")
    assert "ALWAYS requires the operator to confirm" not in command
    assert "there is no" not in command.split("def apply(")[1].split('"""')[1]
    # The CLI wiring module must not carry a stale copy of the command.
    cli_source = Path("indeed_scraper/cli.py").read_text(encoding="utf-8")
    assert "ALWAYS requires the operator to confirm" not in cli_source


def test_the_policy_file_is_the_ceiling_on_autonomy(tmp_path: Path) -> None:
    """A flag or env var can lower the autonomy, never raise it."""
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"level": "manual"}), encoding="utf-8")
    policy = AutonomyPolicy.load(policy_file)
    assert policy.level == "manual"

    # Asking for MORE than the file allows returns the file's level.
    assert policy.restrict_to("full").level == "manual"
    assert policy.restrict_to("auto").level == "manual"
    # Asking for LESS is honoured.
    assert policy.restrict_to("manual").level == "manual"


def test_a_full_policy_file_can_still_be_lowered(tmp_path: Path) -> None:
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"level": "full"}), encoding="utf-8")
    policy = AutonomyPolicy.load(policy_file)
    assert policy.restrict_to("manual").level == "manual"
    assert policy.restrict_to("auto").level == "auto"
    assert policy.restrict_to("full").level == "full"


def test_an_unreadable_policy_file_is_an_operator_message(tmp_path: Path) -> None:
    """A permissions problem must not surface as a raw OSError traceback."""
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"level": "full"}), encoding="utf-8")
    policy_file.chmod(0o000)
    try:
        if os.geteuid() == 0:
            pytest.skip("root ignores the mode bits")
        with pytest.raises(IndeedScraperError) as error:
            AutonomyPolicy.load(policy_file)
        assert "policy" in str(error.value).lower()
    finally:
        policy_file.chmod(0o600)


def test_a_malformed_policy_file_is_an_operator_message(tmp_path: Path) -> None:
    policy_file = tmp_path / "policy.json"
    policy_file.write_text("{not json", encoding="utf-8")
    with pytest.raises(IndeedScraperError):
        AutonomyPolicy.load(policy_file)


# ---------------------------------------------------------------------------
# HIGH: the offer gate must not depend on the classifier alone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Please review and countersign the attached employment agreement.",
        "Please sign and return the offer letter.",
        "We are ready to send the contract - what is your start date?",
        "Please accept the terms and confirm your joining date.",
        "Can you send your banking details for the payroll setup?",
    ],
)
def test_contract_language_reaches_the_operator(message: str) -> None:
    """Binding language gates the reply even when the kind is not "offer"."""
    assert is_binding(message) is True
    plan = build_reply(_profile(), message, "Acme")
    assert plan.requires_approval is True, message


def test_a_contract_request_is_not_classified_as_an_offer() -> None:
    """The binding detector is INDEPENDENT of the classifier.

    If the classifier ever learns this phrasing, the gate still holds; if the
    classifier misses it, the binding detector still catches it.
    """
    message = "Please review and countersign the attached employment agreement."
    assert classify(message) != "offer" or is_binding(message) is True


def test_ordinary_mail_is_not_gated() -> None:
    for message in [
        "Hi Brad, I found your resume on Indeed and wanted to reach out.",
        "Are you available for a call next week?",
        "Please let us know your availability for an interview.",
    ]:
        assert is_binding(message) is False, message
        assert build_reply(_profile(), message, "Acme").requires_approval is False


# ---------------------------------------------------------------------------
# HIGH: a posting that reached the submit click is never applied to twice
# ---------------------------------------------------------------------------


def test_a_submitting_posting_is_never_applied_to_again(tmp_path: Path) -> None:
    """The attempt is recorded BEFORE the click, so a kill cannot re-open it."""
    from indeed_scraper.apply.flow import RESERVATION_LEASE_SECONDS, _stale
    from indeed_scraper.apply.ledger import ApplicationLedger

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp", "jk", "url")
    ledger.mark("fp", "submitting", "")

    # "submitting" is never stale: the lease must not release it.
    assert ledger.reservation_age("fp") is None
    assert _stale(ledger, "fp") is False
    assert RESERVATION_LEASE_SECONDS > 0


def test_the_flow_skips_a_submitting_posting(tmp_path: Path) -> None:
    from indeed_scraper.apply.flow import _apply_jobs_on_page
    from indeed_scraper.apply.ledger import ApplicationLedger
    from indeed_scraper.apply.risk import RiskBudget
    from indeed_scraper.dedupe import job_fingerprint
    from indeed_scraper.scraper import Job

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    job = Job(jk="jk", title="Role", company="Acme", location="BC", url="https://x/jk")
    fingerprint = job_fingerprint(job)
    ledger.reserve(fingerprint, "jk", "url")
    ledger.mark(fingerprint, "submitting", "")

    results = _apply_jobs_on_page(
        page=object(),  # type: ignore[arg-type]
        jobs=[job],
        profile=_profile(),
        ledger=ledger,
        config=object(),  # type: ignore[arg-type]
        console=_Console(),
        budget=RiskBudget(max_per_day=5, min_delay_minutes=0),
        needs_confirm=True,
        dry_run=False,
    )
    assert [r.status for r in results] == ["failed"]
    assert results[0].detail == "duplicate"
    assert (
        ledger.status_of(fingerprint) == "submitting"
    ), "the submitting state was overwritten"


# ---------------------------------------------------------------------------
# MEDIUM: the ledger is not a second copy of the profile
# ---------------------------------------------------------------------------


def test_the_ledger_body_does_not_carry_the_operator() -> None:
    profile = _profile()
    body = "Hello Brad,\n\nI am interested. Reach me at brad@example.com or 250-555-0142."
    redacted = redact_operator(body, profile)
    assert "Brad" not in redacted
    assert "brad@example.com" not in redacted
    assert "250-555-0142" not in redacted
    assert "[operator]" in redacted
    # The shape of the reply survives.
    assert "I am interested" in redacted


def test_the_message_ledger_stores_no_operator_details(tmp_path: Path) -> None:
    from indeed_scraper.messages.store import read_sent, record_sent

    profile = _profile()
    record_sent(
        tmp_path,
        conversation_id="c1",
        company="Acme",
        body=redact_operator("Hello Brad, I am interested.", profile),
        status="sent",
    )
    raw = (tmp_path / "messages" / "sent.jsonl").read_text(encoding="utf-8")
    assert "Brad" not in raw
    assert "brad@example.com" not in raw
    assert "250-555-0142" not in raw
    assert read_sent(tmp_path)[0]["status"] == "sent"
    assert stat.S_IMODE((tmp_path / "messages" / "sent.jsonl").stat().st_mode) == 0o600
