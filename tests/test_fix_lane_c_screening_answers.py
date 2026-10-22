"""C5: a screening answer may only be used on a CONFIDENT match.

The matcher used to be::

    key.lower() in lowered or any(
        word in lowered for word in key.lower().split() if len(word) > 3
    )

A profile key like "years of experience" therefore matched a recruiter's
question about "do you have experience with Excel" - the shared token
"experience" was enough. The reply then carried a FABRICATED answer, and
because the ``question`` branch set ``requires_approval=binding`` (False
here), it was sent unattended.

A shared generic word is not a confident match. An ambiguous question must
be treated as UNANSWERABLE, so the operator approves it.
"""

from __future__ import annotations

from indeed_scraper.apply.profile import Profile
from indeed_scraper.messages.compose import build_reply


def _profile(answers: dict[str, str]) -> Profile:
    return Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path="/tmp/resume.pdf",
        screening_answers=answers,
    )


def test_a_generic_word_is_not_a_confident_match() -> None:
    """"years of experience" must not answer a question about Excel."""
    profile = _profile({"years of experience": "10 years"})
    plan = build_reply(profile, "Do you have experience with Excel?", "Acme")
    assert "10 years" not in plan.body, (
        f"a fabricated answer was sent: {plan.body!r}"
    )
    assert plan.requires_approval is True, (
        "an ambiguous question was answered without the operator"
    )
    assert plan.reason, "a gated reply must say why"


def test_an_exact_match_still_works() -> None:
    """The confident case must keep working: the answer is used."""
    profile = _profile({"work authorization": "Canadian citizen"})
    plan = build_reply(profile, "What is your work authorization status?", "Acme")
    assert "Canadian citizen" in plan.body
    assert plan.requires_approval is False


def test_a_substring_match_still_works() -> None:
    """A key that appears verbatim in the question is a confident match."""
    profile = _profile({"notice period": "2 weeks"})
    plan = build_reply(profile, "What is your notice period?", "Acme")
    assert "2 weeks" in plan.body
    assert plan.requires_approval is False


def test_an_unrelated_question_is_not_answered() -> None:
    """A question about something the profile does not mention is unanswerable."""
    profile = _profile({"work authorization": "Canadian citizen"})
    plan = build_reply(profile, "What is your expected salary?", "Acme")
    assert "Canadian citizen" not in plan.body
    assert plan.requires_approval is True


def test_a_long_shared_token_alone_is_not_a_match() -> None:
    """A single long shared word is not enough; the whole key must line up."""
    profile = _profile({"proficiency with excel macros": "expert"})
    plan = build_reply(profile, "Do you have experience with excel macros?", "Acme")
    # "experience" is shared but the key as a whole is not present.
    assert "expert" not in plan.body
    assert plan.requires_approval is True


def test_a_matched_key_is_only_used_once() -> None:
    """The first confident match wins; a later key cannot override it."""
    profile = _profile(
        {
            "years of experience": "10 years",
            "years of experience in excel": "10 years",
        }
    )
    plan = build_reply(profile, "What is your years of experience?", "Acme")
    assert "10 years" in plan.body
    assert plan.requires_approval is False
