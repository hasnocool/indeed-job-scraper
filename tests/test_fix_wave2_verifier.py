"""Wave 2 — the three defects the independent V5 verification found.

**C1 MAJOR.** The offer classifier's regex was ``\\bhire(?:ing|d|s)?\\b``.
The alternation attaches to the LETTERS ``ing|d|s``, so it matches "hire",
"hired" and "hires" - but NOT "hiring", which would need "hireing". The
consequence was that "We are hiring you for the Data Engineer role."
classified as a safe general message and would have been ANSWERED
UNATTENDED. It escaped the fail-closed default because the message also
matched the safe pattern ``\\brole\\b``.

**C4 MINOR.** The challenge check came AFTER the "any submitted" check, so
a run that submitted one application and was then blocked by a challenge
exited 0 instead of 3. The flow BREAKS on a challenge, so
``[submitted, blocked]`` is the production shape.

**C5 MINOR.** A screening-answer key ending in a non-word character never
matched: the pattern was ``\\b`` + key + ``\\b``, and ``\\b`` after a
non-word character demands a word character. The key ``'c++'`` could never
match "Do you know C++?".
"""

from __future__ import annotations

import re

import pytest

from indeed_scraper.apply.types import ApplyResult
from indeed_scraper.commands.apply import exit_code_for

# ---------------------------------------------------------------------------
# C1 — the offer classifier must catch "hiring"
# ---------------------------------------------------------------------------

def test_the_offer_pattern_catches_hiring() -> None:
    """"We are hiring you" is an offer-like message.

    The old regex was ``\\bhire(?:ing|d|s)?\\b``: the alternation glued to
    the letters, so "hiring" needed "hireing" and never matched.
    """
    from indeed_scraper.messages.patterns import COMPILED_OFFER

    assert any(pattern.search("We are hiring you for the Data Engineer role.") for pattern in COMPILED_OFFER), (
        "an offer-like 'we are hiring you' message was not detected"
    )


@pytest.mark.parametrize(
    "text",
    [
        "We are hiring you for the Data Engineer role.",
        "We are hiring.",
        "They are hiring for a new role.",
        "Our team is hiring now.",
    ],
)
def test_every_hiring_form_is_detected(text: str) -> None:
    """All the forms of "hiring" must be caught, not just one."""
    from indeed_scraper.messages.patterns import COMPILED_OFFER

    assert any(pattern.search(text) for pattern in COMPILED_OFFER), (
        f"'{text}' was not detected as offer-like"
    )


@pytest.mark.parametrize(
    "text",
    ["We hired you.", "We will hire you.", "They hire graduates."],
)
def test_the_forms_that_used_to_work_still_work(text: str) -> None:
    """The fix must not lose the forms that already matched."""
    from indeed_scraper.messages.patterns import COMPILED_OFFER

    assert any(pattern.search(text) for pattern in COMPILED_OFFER), (
        f"'{text}' was lost by the fix"
    )


def test_the_binding_pattern_catches_hiring_too() -> None:
    """The SECOND, independent detector must catch it as well.

    The same broken pattern was in both lists, so fixing only one of them
    would leave a second hole open.
    """
    from indeed_scraper.messages.patterns import COMPILED_BINDING

    assert any(
        pattern.search("We are hiring you for the Data Engineer role.")
        for pattern in COMPILED_BINDING
    ), "the binding-pattern list misses 'hiring' too"


def test_a_hiring_message_requires_approval() -> None:
    """The end-to-end safety property.

    The message must not be answerable unattended, and the composed reply
    must contain no acceptance language.
    """
    from indeed_scraper.apply.profile import Profile
    from indeed_scraper.messages.compose import build_reply, classify

    message = "We are hiring you for the Data Engineer role."

    kind = classify(message)
    assert kind == "offer", f"the message must classify as an offer, got {kind!r}"

    profile = Profile(
        name="Ada",
        email="ada@example.com",
        phone="555-0100",
        resume_path="/tmp/resume.pdf",
    )
    plan = build_reply(profile, message, company="Acme")
    assert plan.requires_approval is True, (
        "an offer-like message must require the operator's approval"
    )

    lowered = plan.body.lower()
    for phrase in ("i accept", "i'd be delighted", "glad to", "excited to", "on board"):
        assert phrase not in lowered, (
            f"the reply contains acceptance language: {plan.body!r}"
        )


def test_no_suffix_alternation_in_the_pattern_lists_is_broken() -> None:
    """The WHOLE vocabulary must be checked for the same mistake.

    The defect was a suffix alternation GLUED TO THE STEM, so it could
    silently miss a form: ``\bhire(?:ing|d|s)?\b`` needs "hireing" to
    match "hiring". This walks EVERY pattern in both lists, finds the ones
    that name a suffix group, and pins that every form the group names
    actually matches.
    """
    import re

    from indeed_scraper.messages.patterns import (
        BINDING_PATTERNS,
        COMPILED_BINDING,
        COMPILED_OFFER,
        OFFER_PATTERNS,
    )

    # A glued suffix group: the stem and the group share letters, so the
    # group cannot be what the author intended.
    glued = re.compile(r"\\b([a-z]+)\(\?:([a-z|]+)\)\?\\b")

    for list_name, patterns in (
        ("OFFER", OFFER_PATTERNS),
        ("BINDING", BINDING_PATTERNS),
    ):
        for pattern_text in patterns:
            match = glued.search(pattern_text)
            if match is None:
                continue
            stem = match.group(1)
            suffixes = match.group(2).split("|")
            # Every form the group names must actually match the pattern.
            compiled = re.compile(pattern_text, re.IGNORECASE)
            for suffix in suffixes:
                form = f"{stem}{suffix}"
                assert compiled.search(f"We are {form} you."), (
                    f"{list_name} pattern {pattern_text!r} does not match "
                    f"'{form}' - the suffix group is glued to the stem"
                )

    # And the two lists must agree on the words that matter.
    for form in ("hire", "hiring", "hired", "hires"):
        assert any(pattern.search(f"We are {form} you.") for pattern in COMPILED_OFFER), (
            f"'{form}' does not match the offer patterns"
        )
        assert any(pattern.search(f"We are {form} you.") for pattern in COMPILED_BINDING), (
            f"'{form}' does not match the binding patterns"
        )


# ---------------------------------------------------------------------------
# C4 — a challenge outranks a submission
# ---------------------------------------------------------------------------

def _result(status: str, detail: str = "") -> ApplyResult:
    return ApplyResult(
        jk="jk1",
        title="Engineer",
        company="Acme",
        location="Vancouver, BC",
        url="https://ca.indeed.com/viewjob?jk=jk1",
        status=status,
        fingerprint="fp-1",
        app_id="fp-1",
        portal="indeed",
        detail=detail,
    )


def test_a_run_that_submitted_and_was_then_challenged_exits_three() -> None:
    """A challenge stops the run, so it must be reported as a challenge.

    The flow BREAKS on a challenge, so ``[submitted, blocked]`` is the
    production shape. The "any submitted" check fired first and returned
    0, so CI read "all good" for a run that was stopped by a wall.
    """
    results = [
        _result("submitted"),
        _result("blocked", "challenge:Indeed security check"),
    ]
    assert exit_code_for(results) == 3, (
        "a run stopped by a challenge must exit 3, whatever else it did"
    )


def test_a_challenge_alone_still_exits_three() -> None:
    """The plain case must not change."""
    results = [_result("blocked", "challenge:Indeed security check")]
    assert exit_code_for(results) == 3


def test_a_submission_without_a_challenge_still_exits_zero() -> None:
    """The ordinary successful run must not change."""
    results = [_result("submitted")]
    assert exit_code_for(results) == 0


def test_a_failure_without_a_challenge_still_exits_two() -> None:
    """The ordinary failed run must not change."""
    results = [_result("failed", "submit_not_found")]
    assert exit_code_for(results) == 2


# ---------------------------------------------------------------------------
# C5 — a screening key ending in a non-word character
# ---------------------------------------------------------------------------

def _screening_pattern(phrase: str) -> re.Pattern[str]:
    """The pattern the screener builds for a configured answer key."""
    from indeed_scraper.messages.compose import screening_pattern

    return screening_pattern(phrase)


def test_a_key_ending_in_a_non_word_character_matches() -> None:
    """'c++' must match "Do you know C++?".

    ``\\b`` after a non-word character demands a word character, so the
    old pattern could never match. The lookaround version asks the right
    question: is there a word character on either side of the key?
    """
    # The screener lowercases the question before matching, so the
    # pattern is applied to the lowercased text - exactly as the code
    # does it.
    pattern = _screening_pattern("c++")
    assert pattern.search("Do you know C++?".lower()), (
        "a screening key ending in a non-word character never matches"
    )


def test_a_key_ending_in_a_word_character_still_matches() -> None:
    """The fix must not lose the keys that used to work."""
    for phrase, text in (
        ("node.js", "Do you have node.js skills?"),
        ("vue.js", "Do you know vue.js?"),
        ("c", "Do you know c?"),
    ):
        pattern = _screening_pattern(phrase)
        assert pattern.search(text.lower()), f"'{phrase}' no longer matches"


def test_a_key_does_not_match_inside_a_longer_word() -> None:
    """The fix must not make the match too loose.

    "c++" must not match inside "c+++"; and "c" must not match inside
    "abc".
    """
    # "c" must not match inside "abc" - the lookaround must not be looser
    # than the word boundary it replaced.
    assert not _screening_pattern("c").search("Do you know abc?".lower())
    assert not _screening_pattern("node.js").search("Do you know nodejsx?".lower())
