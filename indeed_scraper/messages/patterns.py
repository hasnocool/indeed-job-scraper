"""The vocabulary that decides whether a recruiter message needs a human.

The patterns live in their own module because they are the safety-critical
part of the messaging stack and they are read on their own: a reviewer can
audit this file without reading the composer.

Two lists, with two different jobs.

``OFFER_PATTERNS``
    Phrases that mean a job is being OFFERED, or that the candidate is being
    accepted. A match makes the message an "offer".

``BINDING_PATTERNS``
    Phrases that mean a COMMITMENT is being made, whatever the message is
    otherwise about - a contract, a signature, a start date, payroll details.
    A match means a human must look, even if the classifier did not
    recognise the message.

``SAFE_PATTERNS``
    The narrow list of messages that are clearly about a role and nothing
    more, and may therefore be answered unattended.

The direction of the default is the point. A message that plausibly conveys
an offer, an offer-like acceptance, or a commitment must NEVER go out
unattended, and a message the classifier does not recognise must not go out
unattended either. Only the narrow, clearly-safe categories may be sent
alone - a false positive only holds a reply for the operator, while a false
negative accepts their job for them.

Every phrasing here was a real miss at some point. They are listed so a
future change cannot silently reopen the hole.
"""

from __future__ import annotations

import re

#: Phrases that indicate an offer or another binding commitment.
OFFER_PATTERNS = (
    r"\boffer(?:s|ed|ing)?\b",
    r"\bhire(?:ing|d|s)?\b",
    r"\baccept(?:ance)? (?:of|the|our|this|an|it)\b",
    r"\baccept(?:ance)? of\b",
    r"\bjoining us\b",
    r"\bjoin (?:us|our team)\b",
    r"\bplease (?:confirm|sign)\b",
    r"\bformal (?:offer|appointment|contract)\b",
    r"\bemployment agreement\b",
    r"\bstart (?:date|your employment)\b",
    r"\bstarting (?:on|from|january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\bsalary of\b",
    r"\bcompensation (?:package|offer)\b",
    r"\bcongratulations\b",
    # "We are excited to have you on board." - the phrasing that reopened the
    # hole commit a725653 claimed to close. An acceptance in plain words.
    r"\bon board\b",
    r"\bwelcome (?:aboard|you to the team|to the team)\b",
    r"\bglad to have you\b",
    r"\bpleased to (?:have|welcome)\b",
    r"\bexcited to have you\b",
    r"\bexcited to welcome\b",
    r"\bhappy to have you join\b",
    r"\bmove forward\b",
    r"\bproceed with the next steps\b",
    r"\bextend (?:an |you an )?offer\b",
    r"\bnext steps to extend\b",
    r"\boffer (?:and|&) compensation\b",
    r"\bcompensation details\b",
)

#: Phrases that mark a message as clearly about a role and nothing more -
#: ordinary recruiting mail that may be answered unattended.
SAFE_PATTERNS = (
    r"\bresume\b",
    r"\brole\b",
    r"\breach out\b",
    r"\bgreat fit\b",
    r"\binterested\b",
    r"\blooking for\b",
    r"\bposition\b",
    r"\bopportunity\b",
)

#: Phrases that indicate an interview or scheduling request.
INTERVIEW_PATTERNS = (
    r"\binterview\b",
    r"\bmeet(?:ing)?\b",
    r"\bcall\b",
    r"\bschedule\b",
    r"\bavailable\b",
    r"\bavailability\b",
    r"\bphone screen\b",
    r"\bcoffee chat\b",
    r"\bwhen are you (?:available|free)\b",
)

#: Phrases that indicate a question the operator must answer.
QUESTION_PATTERNS = (
    r"\?$",
    r"\bcan you\b",
    r"\bcould you\b",
    r"\bwould you\b",
    r"\bdo you\b",
    r"\bplease (?:confirm|let us know|share|send)\b",
    r"\bwhat is your\b",
    r"\bhow much\b",
)

#: A SECOND, independent detector for binding language. The offer patterns
#: above classify a message; these say "this needs a human" whatever the
#: message turned out to be about. A contract request that happens not to
#: look like an offer still reaches the operator.
BINDING_PATTERNS = (
    r"\bcountersign\b",
    r"\bemployment agreement\b",
    r"\bcontract\b",
    r"\bsign(?:ed|ature|ing)?\b",
    r"\bsignature\b",
    r"\boffer letter\b",
    r"\bterms and conditions\b",
    r"\baccept the terms\b",
    r"\btax form\b",
    r"\bnon[- ]?disclosure\b",
    r"\bwork permit\b",
    r"\bbanking details\b",
    r"\bSIN\b",
    r"\bstart date\b",
    r"\bjoining date\b",
    r"\bon board\b",
    r"\boffer(?:s|ed|ing)?\b",
    r"\baccept(?:ance)? (?:of|the|our|this|an|it)\b",
    r"\baccept(?:ance)? of\b",
    r"\byou will be (?:joining|starting|on)\b",
)


def _compile(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Compile a pattern list once, case-insensitively."""
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


COMPILED_OFFER = _compile(OFFER_PATTERNS)
COMPILED_SAFE = _compile(SAFE_PATTERNS)
COMPILED_INTERVIEW = _compile(INTERVIEW_PATTERNS)
COMPILED_QUESTION = _compile(QUESTION_PATTERNS)
COMPILED_BINDING = _compile(BINDING_PATTERNS)
