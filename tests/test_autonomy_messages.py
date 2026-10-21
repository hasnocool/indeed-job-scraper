"""Tests for the autonomy policy and the recruiter-message composer.

The policy decides what the agent may do unattended, and the composer decides
what a reply says and whether it may be sent alone.
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
from indeed_scraper.messages.compose import build_reply, classify
from indeed_scraper.messages.store import already_replied, read_sent, record_sent


def _profile(**overrides: object) -> Profile:
    base = {
        "name": "Brad Cooper",
        "email": "brad@example.com",
        "phone": "250-555-0142",
        "resume_path": "/tmp/resume.pdf",
        "availability": "next week",
        "screening_answers": {"work authorization": "Canadian citizen"},
    }
    base.update(overrides)
    return Profile(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Autonomy policy
# ---------------------------------------------------------------------------


def test_missing_policy_file_falls_back_to_the_safe_default(tmp_path: Path) -> None:
    """A fresh install must be conservative, not permissive."""
    policy = AutonomyPolicy.load(tmp_path / "nope.json")
    assert policy.level == "manual"
    assert policy.allows_submit is False
    assert policy.allows_reply is False
    assert policy.allows_binding_commitment is False


def test_policy_is_read_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "level": "full",
                "max_applications_per_day": 40,
                "min_delay_minutes": 5,
                "allow_binding_commitments": True,
            }
        ),
        encoding="utf-8",
    )
    policy = AutonomyPolicy.load(path)
    assert policy.level == "full"
    assert policy.allows_submit is True
    assert policy.allows_reply is True
    assert policy.allows_binding_commitment is True
    assert policy.max_applications_per_day == 40
    assert policy.min_delay_minutes == 5


def test_an_unknown_level_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"level": "yolo"}), encoding="utf-8")
    with pytest.raises(IndeedScraperError):
        AutonomyPolicy.load(path)


def test_the_level_decides_what_is_allowed(tmp_path: Path) -> None:
    manual = AutonomyPolicy(level="manual")
    auto = AutonomyPolicy(level="auto")
    full = AutonomyPolicy(level="full")
    assert manual.allows_submit is False and manual.allows_reply is False
    assert auto.allows_submit is True and auto.allows_reply is False
    assert full.allows_submit is True and full.allows_reply is True


def test_saved_policy_is_private_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    AutonomyPolicy(level="auto", max_applications_per_day=7).save(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert AutonomyPolicy.load(path).max_applications_per_day == 7


# ---------------------------------------------------------------------------
# Message classification
# ---------------------------------------------------------------------------


def test_an_offer_is_classified_as_an_offer() -> None:
    assert classify("We would like to offer you the position. Let us know your start date.") == "offer"


def test_an_interview_request_is_classified_as_an_interview() -> None:
    assert classify("Are you available for a call next week?") == "interview"


def test_a_question_is_classified_as_a_question() -> None:
    assert classify("What is your expected salary?") == "question"


def test_a_plain_message_is_general() -> None:
    assert classify("I found your resume and wanted to reach out.") == "general"


def test_an_empty_message_is_unknown() -> None:
    assert classify("   ") == "unknown"


# ---------------------------------------------------------------------------
# Reply building
# ---------------------------------------------------------------------------


def test_an_offer_reply_always_requires_approval() -> None:
    plan = build_reply(_profile(), "We would like to offer you the role.")
    assert plan.kind == "offer"
    assert plan.requires_approval is True
    assert "offer" in plan.reason.lower() or "binding" in plan.reason.lower()


def test_an_interview_reply_uses_the_availability_from_the_profile() -> None:
    plan = build_reply(_profile(availability="from Monday"), "Can we schedule a call?")
    assert plan.kind == "interview"
    assert plan.requires_approval is False
    assert "from Monday" in plan.body


def test_a_question_the_profile_answers_needs_no_approval() -> None:
    plan = build_reply(_profile(), "What is your work authorization status?")
    assert plan.kind == "question"
    assert plan.requires_approval is False
    assert "Canadian citizen" in plan.body


def test_a_question_the_profile_cannot_answer_requires_approval() -> None:
    plan = build_reply(_profile(screening_answers={}), "What is your expected salary?")
    assert plan.requires_approval is True
    assert plan.reason


def test_a_general_reply_is_sent_without_approval() -> None:
    plan = build_reply(_profile(), "I saw your resume and thought you could be a great fit.")
    assert plan.kind == "general"
    assert plan.requires_approval is False
    assert "Brad" in plan.body


# ---------------------------------------------------------------------------
# Message ledger
# ---------------------------------------------------------------------------


def test_sent_messages_are_recorded_and_deduplicated(tmp_path: Path) -> None:
    state = tmp_path / "state"
    record_sent(
        state,
        conversation_id="conv-1",
        company="Acme",
        body="Hello,",
        status="sent",
    )
    assert already_replied(state, "conv-1") is True
    assert already_replied(state, "conv-2") is False
    entries = read_sent(state)
    assert len(entries) == 1
    assert entries[0]["company"] == "Acme"
    assert entries[0]["body"] == "Hello,"


def test_a_drafted_reply_does_not_count_as_replied(tmp_path: Path) -> None:
    state = tmp_path / "state"
    record_sent(
        state,
        conversation_id="conv-1",
        company="Acme",
        body="Hello,",
        status="drafted",
    )
    assert already_replied(state, "conv-1") is False


def test_the_ledger_survives_a_malformed_line(tmp_path: Path) -> None:
    state = tmp_path / "state"
    record_sent(state, conversation_id="c1", company="A", body="x", status="sent")
    path = state / "messages" / "sent.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    entries = read_sent(state)
    assert len(entries) == 1
    assert entries[0]["conversation_id"] == "c1"


def test_the_ledger_is_private(tmp_path: Path) -> None:
    state = tmp_path / "state"
    record_sent(state, conversation_id="c1", company="A", body="x", status="sent")
    path = state / "messages" / "sent.jsonl"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert os.path.isdir(state / "messages")
