"""C1: the offer classifier must FAIL CLOSED.

The classifier used to be an allow-list of offer phrases. A recruiter message
that used none of them ("We are excited to have you on board.") was classified
``general`` and was sent unattended, because the default was "safe" and only
the listed phrasings were dangerous.

The direction of the default is the whole point: a message that plausibly
conveys an offer, an offer-like acceptance, or a commitment must NEVER be
sent unattended, and an unrecognised recruiter message must not be sent
unattended either. Only the narrow, clearly-safe categories may go out alone.

These tests are hermetic: no browser, no network, no operator profile on
disk.
"""

from __future__ import annotations

import pytest

from indeed_scraper.apply.profile import Profile
from indeed_scraper.messages.compose import build_reply, is_binding

#: Recruiter mail that carries an offer, an offer-like acceptance, or a
#: commitment. Every one of them must reach the operator.
OFFER_LIKE = [
    # The phrasing that reopened the hole commit a725653 claimed to close.
    "We are excited to have you on board.",
    "Welcome aboard the team - we are glad to have you.",
    "We'd like to move forward with you and extend an offer for the role.",
    "Let's proceed with the next steps to extend an offer.",
    "Your offer and compensation details are attached.",
    "Following our interview, we would like to move forward with you.",
    "We are happy to have you join us starting June 1.",
    "Congratulations! We are excited to have you on board.",
    "We would like to offer you the position.",
    "We are pleased to welcome you to the team.",
]

#: Recruiter mail that is clearly about a role and nothing more. These may
#: still be answered unattended, or the agent is useless.
CLEARLY_SAFE = [
    "Hi Brad, I found your resume on Indeed and wanted to reach out about a role.",
    "Are you available for a call next week?",
    "Please let us know your availability for an interview.",
    "I saw your resume and thought you could be a great fit.",
    "Hi Brad, I found your resume on Indeed and wanted to reach out.",
]

#: Recruiter mail the classifier does not recognise. The default is "a human
#: looks at this", NOT "this is safe".
UNRECOGNISED = [
    "We would like to proceed with the next steps of the hiring process.",
    "Your background caught our attention and we would like to keep talking.",
]


def _profile() -> Profile:
    return Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path="/tmp/resume.pdf",
        availability="next week",
        screening_answers={"work authorization": "Canadian citizen"},
    )


@pytest.mark.parametrize("text", OFFER_LIKE)
def test_an_offer_like_message_never_goes_out_alone(text: str) -> None:
    """The classifier may not call an offer-like message ordinary mail."""
    plan = build_reply(_profile(), text, "Acme")
    assert plan.requires_approval is True, f"would be sent unattended: {text!r}"
    assert plan.kind == "offer", (
        f"classified as {plan.kind!r} instead of an offer: {text!r}"
    )


@pytest.mark.parametrize("text", CLEARLY_SAFE)
def test_a_clearly_safe_message_is_not_over_gated(text: str) -> None:
    """The gate must not swallow every message, or the agent is useless."""
    plan = build_reply(_profile(), text, "Acme")
    assert plan.requires_approval is False, f"over-gated: {text!r}"


@pytest.mark.parametrize("text", UNRECOGNISED)
def test_an_unrecognised_message_requires_a_human(text: str) -> None:
    """The default is "requires approval"; a safe reply is the exception."""
    plan = build_reply(_profile(), text, "Acme")
    assert plan.requires_approval is True, f"sent unattended by default: {text!r}"
    assert plan.reason, "a gated reply must say why"


def test_the_named_defect_is_fixed() -> None:
    """The exact message from the review that proved the hole."""
    text = "We are excited to have you on board."
    plan = build_reply(_profile(), text, "Acme")
    assert plan.requires_approval is True
    assert plan.kind == "offer"
    assert is_binding(text) is True, (
        "the binding detector must catch an acceptance as well as the classifier"
    )


def test_the_offer_reply_never_contains_an_acceptance() -> None:
    """Even a drafted offer reply must not say yes on the operator's behalf."""
    plan = build_reply(_profile(), "We are excited to have you on board.", "Acme")
    body = plan.body.lower()
    for phrase in ("i accept", "accepted", "i will take the job", "on board"):
        assert phrase not in body, f"the draft already accepts: {plan.body!r}"


def test_the_gated_reply_still_says_something_sensible() -> None:
    """A held reply must still be a reply the operator can send."""
    plan = build_reply(_profile(), "We are excited to have you on board.", "Acme")
    assert plan.body.strip()
    assert "Brad" in plan.body
