"""Regression tests for the findings of the two independent BLOCK reviews.

Each test here corresponds to a finding that was a real defect, so a future
change that reintroduces it fails loudly.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from indeed_scraper.apply.autonomy import AutonomyPolicy
from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.profile import Profile
from indeed_scraper.errors import IndeedScraperError
from indeed_scraper.messages.compose import build_reply, is_binding, redact_operator
from indeed_scraper.messages.store import already_replied, record_sent


def _profile() -> Profile:
    return Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path="/tmp/resume.pdf",
    )


# ---------------------------------------------------------------------------
# CRITICAL: the policy file is the ceiling on autonomy
# ---------------------------------------------------------------------------


def test_the_policy_file_caps_the_autonomy(tmp_path: Path) -> None:
    """A CLI flag may lower the autonomy, never raise it above the file.

    The file is the operator's standing decision; a stray flag (or a typo in
    an environment variable) must not grant more autonomy than they allowed.
    """
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"level": "manual"}), encoding="utf-8")
    policy = AutonomyPolicy.load(path)
    assert policy.level == "manual"
    # Asking for full is capped at what the file allows.
    assert policy.restrict_to("full").level == "manual"
    # Asking for manual is honoured.
    assert policy.restrict_to("manual").level == "manual"


def test_a_full_policy_file_may_be_lowered_but_not_raised(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"level": "full"}), encoding="utf-8")
    policy = AutonomyPolicy.load(path)
    assert policy.restrict_to("manual").level == "manual"
    assert policy.restrict_to("auto").level == "auto"
    assert policy.restrict_to("full").level == "full"


def test_an_unreadable_policy_file_is_an_operator_message(tmp_path: Path) -> None:
    """A permissions problem must not surface as a traceback."""
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"level": "full"}), encoding="utf-8")
    path.chmod(0o000)
    try:
        with pytest.raises(IndeedScraperError) as error:
            AutonomyPolicy.load(path)
        assert "Cannot read the policy file" in str(error.value)
    finally:
        path.chmod(0o600)


# ---------------------------------------------------------------------------
# HIGH: a contract request is gated even when it is not an "offer"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Please review and countersign the attached employment agreement.",
        "Please find the contract attached for your signature.",
        "We need your banking details for payroll before your start date.",
        "Please sign and return the offer letter.",
        "Please accept the terms and conditions attached.",
    ],
)
def test_binding_language_is_gated_whatever_the_classifier_says(message: str) -> None:
    """The binding detector is independent of the offer classifier."""
    assert is_binding(message) is True
    plan = build_reply(_profile(), message, "Acme")
    assert plan.requires_approval is True, message


def test_ordinary_recruiter_mail_is_not_binding() -> None:
    for message in (
        "Hi Brad, I found your resume on Indeed and wanted to reach out.",
        "Are you available for a call next week?",
        "What is your expected salary?",
    ):
        assert is_binding(message) is False, message


# ---------------------------------------------------------------------------
# HIGH: a posting that reached the submit click is never applied to twice
# ---------------------------------------------------------------------------


def test_a_submitting_posting_is_never_re_applied(tmp_path: Path) -> None:
    """A run killed between the submit click and the mark leaves "submitting".

    That state must never be released by the stale-reservation lease: a
    duplicate application is worse than a missed one.
    """
    from indeed_scraper.apply.flow import _stale

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp1", "jk1", "https://example.invalid")
    ledger.mark("fp1", "submitting", "")

    assert ledger.status_of("fp1") == "submitting"
    # The lease only expires a plain reservation, never a submission attempt.
    assert ledger.reservation_age("fp1") is None
    assert _stale(ledger, "fp1") is False


def test_a_stale_reservation_is_still_released(tmp_path: Path) -> None:
    """A run killed BEFORE the submit click must not block the posting."""

    from indeed_scraper.apply.flow import RESERVATION_LEASE_SECONDS, _stale

    path = tmp_path / "ledger.jsonl"
    old = datetime.now(tz=timezone.utc) - timedelta(seconds=RESERVATION_LEASE_SECONDS + 600)
    path.write_text(
        json.dumps(
            {
                "fingerprint": "fp2",
                "jk": "jk2",
                "indeed_url": "u",
                "company": "",
                "title": "",
                "applied_at": old.isoformat(),
                "status": "reserved",
                "detail": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ledger = ApplicationLedger(path)
    assert _stale(ledger, "fp2") is True


# ---------------------------------------------------------------------------
# HIGH: the dedupe key and the record key are the same key
# ---------------------------------------------------------------------------


def test_an_unknown_conversation_id_fails_closed(tmp_path: Path) -> None:
    """Without a stable id a conversation cannot be recognised later."""
    assert already_replied(tmp_path, "") is True


def test_a_sending_record_counts_as_answered(tmp_path: Path) -> None:
    """A run killed after the send must not produce a second reply."""
    record_sent(
        tmp_path,
        conversation_id="conv1",
        company="Acme",
        body="Hello,",
        status="sending",
    )
    assert already_replied(tmp_path, "conv1") is True


# ---------------------------------------------------------------------------
# MEDIUM: the operator's details live in the profile, not in a second store
# ---------------------------------------------------------------------------


def test_the_reply_body_is_redacted_before_it_is_stored() -> None:
    profile = _profile()
    body = "Hello Brad,\n\nReach me on brad@example.com or 250-555-0142."
    redacted = redact_operator(body, profile)
    assert "Brad" not in redacted
    assert "brad@example.com" not in redacted
    assert "250-555-0142" not in redacted
    assert "[operator]" in redacted
    # The shape of the message survives.
    assert "Hello" in redacted


def test_the_stored_message_never_carries_the_operator_details(tmp_path: Path) -> None:
    profile = _profile()
    record_sent(
        tmp_path,
        conversation_id="conv1",
        company="Acme",
        body=redact_operator("Hello Brad, I am interested.", profile),
        status="sent",
    )
    raw = (tmp_path / "messages" / "sent.jsonl").read_text(encoding="utf-8")
    assert "Brad" not in raw
    assert "brad@example.com" not in raw
    assert profile.phone not in raw
