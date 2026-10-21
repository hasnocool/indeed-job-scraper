"""The offer gate must not have holes.

An offer acceptance is a binding commitment made on the operator's behalf. A
classifier that lets one through would send "I'll take it" without the
operator ever seeing it, so the offer class is deliberately broad: a false
positive only holds a reply for the operator, while a false negative accepts
their job for them.

Every phrasing in ``OFFER_PHRASINGS`` was a real miss at some point; they are
listed here so a future change to the patterns cannot silently reopen the hole.
"""

from __future__ import annotations

import pytest

from indeed_scraper.apply.profile import Profile
from indeed_scraper.messages.compose import build_reply, classify

OFFER_PHRASINGS = [
    "We would like to offer you the position.",
    "We'd like to extend an offer for the role.",
    "Congratulations! We are offering you the job.",
    "Please confirm your acceptance of our offer.",
    "Please sign and return the formal offer letter.",
    "We would like to hire you. What is your start date?",
    "Please sign the employment agreement and confirm your start date.",
    "Your offer includes a salary of $95,000.",
    "Please let us know if you can join us starting June 1.",
    "Can you confirm you accept the compensation package?",
    "Following our interview, we would like to move forward with an offer.",
]

#: Ordinary recruiter mail that must keep flowing without the operator.
ORDINARY_PHRASINGS = [
    "Hi Brad, I found your resume on Indeed and wanted to reach out about a role.",
    "Are you available for a call next week?",
    "Please let us know your availability for an interview.",
]


def _profile() -> Profile:
    return Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path="/tmp/resume.pdf",
    )


@pytest.mark.parametrize("text", OFFER_PHRASINGS)
def test_an_offer_phrase_is_never_answered_alone(text: str) -> None:
    """Every known offer phrasing is classified as an offer AND needs approval."""
    assert classify(text) == "offer", f"not classified as an offer: {text!r}"
    plan = build_reply(_profile(), text, "Acme")
    assert plan.requires_approval is True, f"would be sent unattended: {text!r}"


@pytest.mark.parametrize("text", ORDINARY_PHRASINGS)
def test_ordinary_recruiter_mail_is_not_over_gated(text: str) -> None:
    """The gate must not swallow every message, or the agent is useless."""
    plan = build_reply(_profile(), text, "Acme")
    assert plan.requires_approval is False, f"over-gated: {text!r}"


def test_the_offer_reply_never_contains_an_acceptance() -> None:
    """Even the drafted offer reply must not say yes on the operator's behalf."""
    plan = build_reply(_profile(), "We would like to offer you the role.", "Acme")
    body = plan.body.lower()
    for phrase in ("i accept", "i accept the offer", "accepted", "i will take the job"):
        assert phrase not in body, f"the draft already accepts: {plan.body!r}"
