"""Decide what to say back to a recruiter, and whether it may be said alone.

The composer is rule-based: it reads the incoming message, classifies it, and
builds a reply from the operator's profile. There is no language model in the
loop, so the wording is predictable and the operator can see exactly what
will be sent before it is sent.

The default is "a human looks at it". A reply only goes out alone when the
message is one of the narrow, clearly-safe categories - an interview request
or an ordinary note about a role. Everything else, including a message the
classifier does not recognise, is held for the operator. The direction matters:
a false positive only holds a reply for a minute, while a false negative
accepts the operator's job for them.

The pattern vocabulary lives in :mod:`indeed_scraper.messages.patterns` so it
can be audited on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..apply.profile import Profile
from .patterns import (
    BINDING_PATTERNS,
    COMPILED_BINDING,
    COMPILED_INTERVIEW,
    COMPILED_OFFER,
    COMPILED_QUESTION,
    COMPILED_SAFE,
    INTERVIEW_PATTERNS,
    OFFER_PATTERNS,
    QUESTION_PATTERNS,
    SAFE_PATTERNS,
)

MessageKind = Literal["offer", "interview", "question", "general", "unknown"]

__all__ = [
    "BINDING_PATTERNS",
    "INTERVIEW_PATTERNS",
    "OFFER_PATTERNS",
    "QUESTION_PATTERNS",
    "SAFE_PATTERNS",
    "MessageKind",
    "ReplyPlan",
    "build_reply",
    "classify",
    "is_binding",
    "redact_operator",
]


@dataclass(frozen=True, slots=True)
class ReplyPlan:
    """What to reply, and under what conditions."""

    kind: MessageKind
    body: str
    requires_approval: bool
    reason: str = ""


def is_binding(text: str) -> bool:
    """True when the message contains binding or contractual language.

    This is deliberately independent of :func:`classify`: the classifier
    decides what to SAY, this decides whether a HUMAN must look first. A
    contract request that happens not to look like an offer still reaches the
    operator.
    """
    if not text or not text.strip():
        return False
    return any(pattern.search(text) for pattern in COMPILED_BINDING)


def redact_operator(body: str, profile: Profile) -> str:
    """Remove the operator's own details from a message body.

    The ledger is an audit trail of what was said, not a second copy of the
    profile: the operator's name, email and phone live in the 0600 profile
    only. The structure of the reply is preserved.
    """
    if not body:
        return body
    redacted = body
    values: list[str] = []
    if profile.email:
        values.append(profile.email)
    if profile.phone:
        values.append(profile.phone)
    name = profile.name.strip()
    if name:
        values.append(name)
        parts = [part for part in name.split() if part]
        if len(parts) > 1:
            values.append(parts[0])
    for value in sorted(values, key=len, reverse=True):
        if value:
            redacted = redacted.replace(value, "[operator]")
    return redacted


def classify(text: str) -> MessageKind:
    """Classify an incoming message.

    The kinds are ordered by how much they matter: an offer outranks an
    interview, which outranks a question. A message that matches none of the
    known shapes is "unknown" - and "unknown" is NOT "safe to send alone".
    """
    if not text.strip():
        return "unknown"
    if any(pattern.search(text) for pattern in COMPILED_OFFER):
        return "offer"
    if any(pattern.search(text) for pattern in COMPILED_INTERVIEW):
        return "interview"
    if any(pattern.search(text) for pattern in COMPILED_QUESTION):
        return "question"
    if any(pattern.search(text) for pattern in COMPILED_SAFE):
        return "general"
    return "unknown"


def _availability(profile: Profile) -> str:
    if profile.availability:
        return profile.availability
    return "my availability, which I am happy to confirm once we agree on a time"


def _answer_for(profile: Profile, question: str) -> str | None:
    """Answer a question from the profile's screening answers, on a CONFIDENT match only.

    A match is confident when the whole key appears as a whole-word phrase in
    the question. A shared generic word (or one key inside another, such as
    "java" inside "javascript") is deliberately NOT enough - an unconfident
    match means "unanswerable", so the operator approves the reply.
    """
    if not profile.screening_answers:
        return None
    lowered = question.lower()
    for key, answer in profile.screening_answers.items():
        phrase = key.strip().lower()
        if not phrase:
            continue
        if screening_pattern(phrase).search(lowered):
            return answer
    return None


def screening_pattern(phrase: str) -> re.Pattern[str]:
    """The pattern that matches a configured screening-answer key.

    The key is matched with LOOKAROUND, not with ``\b``. ``\b`` is a
    boundary between a word character and a non-word one, so ``\b`` after
    a non-word character demands a word character and can never be
    satisfied: the key "c++" could never match "Do you know C++?", and
    the operator's configured answer silently never applied.

    The lookaround asks the right question - is there a word character on
    either side of the key? - and it works for every key, whether it ends
    in a word character or not.
    """
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)")


_CORPORATE_SUFFIXES = ("inc", "ltd", "llc", "corp", "co", "gmbh", "plc", "sa", "systems", "services")


def _role_phrase(company: str) -> str:
    """How to refer to the opportunity in the reply.

    Indeed shows the contact's name when a posting has no company name, so
    "the role at Youmna Soliman" would read oddly - that case is phrased as
    "the role you mentioned".
    """
    name = company.strip().rstrip(".")
    if not name:
        return "the role"
    lowered = name.lower()
    looks_like_a_company = any(
        word in lowered for word in _CORPORATE_SUFFIXES
    ) or len(name.split()) > 2
    if not looks_like_a_company:
        return "the role you mentioned"
    return f"the role at {name}"


def build_reply(profile: Profile, incoming: str, company: str = "") -> ReplyPlan:
    """Build the reply for an incoming message.

    An offer always requires the operator's approval: it is a binding
    commitment, and the reply is never sent unattended by this function.
    """
    kind = classify(incoming)
    binding = is_binding(incoming)
    role = _role_phrase(company)
    salutation = f"Hello{',' if not profile.name else ' ' + profile.name.split()[0]},"

    if kind == "offer":
        return ReplyPlan(
            kind=kind,
            body=(
                f"{salutation}\n\nThank you for the offer - I am very interested in the role. "
                "Let me review the details and come back to you shortly."
            ),
            requires_approval=True,
            reason="accepting or agreeing to terms is a binding commitment",
        )

    if kind == "interview":
        return ReplyPlan(
            kind=kind,
            body=(
                f"{salutation}\n\nThank you for reaching out about {role}. "
                f"I am interested and available - {_availability(profile)}. "
                "Please let me know what times work for you."
            ),
                requires_approval=binding,
                reason=("the message contains binding or contractual language" if binding else ""),
        )

    if kind == "question":
        answer = _answer_for(profile, incoming)
        if answer:
            return ReplyPlan(
                kind=kind,
                body=f"{salutation}\n\n{answer}\n\nLet me know if you need anything else from me.",
                requires_approval=binding,
                reason=("the message contains binding or contractual language" if binding else ""),
            )
        return ReplyPlan(
            kind=kind,
            body=(
                f"{salutation}\n\nThank you for your message. I am interested in {role}. "
                "I will get back to you with the details shortly."
            ),
            requires_approval=True,
            reason="the question is not answerable from the profile",
        )

    if kind == "unknown":
        # Fail closed: an unrecognised recruiter message is never sent
        # unattended - only the narrow, clearly-safe categories may go out alone.
        return ReplyPlan(
            kind=kind,
            body=(
                f"{salutation}\n\nThank you for your message about {role}. "
                "I am interested and will get back to you with details shortly."
            ),
            requires_approval=True,
            reason="the message was not recognised; it needs a person's review",
        )

    return ReplyPlan(
        kind=kind,
        body=(
            f"{salutation}\n\nThank you for reaching out about {role}. "
            "I am interested and would be happy to talk. Please let me know the next steps."
        ),
        requires_approval=binding,
        reason=("the message contains binding or contractual language" if binding else ""),
    )
