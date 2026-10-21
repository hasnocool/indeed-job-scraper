"""Decide what to say back to a recruiter, and whether it may be said alone.

The composer is rule-based: it reads the incoming message, classifies it, and
builds a reply from the operator's profile. There is no language model in the
loop, so the wording is predictable and the operator can see exactly what
will be sent before it is sent.

One class of reply is never sent unattended unless the policy explicitly
allows it: a reply that accepts an offer or agrees to contractual terms
(``offer_received``). That is a binding commitment made on the operator's
behalf, and the surface it arrives on is a recruiter's message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..apply.profile import Profile

MessageKind = Literal["offer", "interview", "question", "general", "unknown"]

#: Phrases that indicate an offer or another binding commitment.
OFFER_PATTERNS = (
    r"\boffer\b",
    r"\bplease (?:confirm|sign)\b",
    r"\bwe(?:'d| would) like to (?:offer|hire)\b",
    r"\bformal (?:offer|appointment)\b",
    r"\bstart (?:date|your employment)\b",
    r"\bjoin our team\b",
    r"\bsalary of\b",
    r"\bcompensation package\b",
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

_COMPILED = {
    "offer": [re.compile(p, re.IGNORECASE) for p in OFFER_PATTERNS],
    "interview": [re.compile(p, re.IGNORECASE) for p in INTERVIEW_PATTERNS],
    "question": [re.compile(p, re.IGNORECASE) for p in QUESTION_PATTERNS],
}


@dataclass(frozen=True, slots=True)
class ReplyPlan:
    """What to reply, and under what conditions."""

    kind: MessageKind
    body: str
    requires_approval: bool
    reason: str = ""


def classify(text: str) -> MessageKind:
    """Classify an incoming message."""
    if not text.strip():
        return "unknown"
    if any(pattern.search(text) for pattern in _COMPILED["offer"]):
        return "offer"
    if any(pattern.search(text) for pattern in _COMPILED["interview"]):
        return "interview"
    if any(pattern.search(text) for pattern in _COMPILED["question"]):
        return "question"
    return "general"


def _availability(profile: Profile) -> str:
    if profile.availability:
        return profile.availability
    return "my availability, which I am happy to confirm once we agree on a time"


def _answer_for(profile: Profile, question: str) -> str | None:
    """Answer a question from the profile's screening answers, when we can."""
    if not profile.screening_answers:
        return None
    lowered = question.lower()
    for key, answer in profile.screening_answers.items():
        if key.lower() in lowered or any(
            word in lowered for word in key.lower().split() if len(word) > 3
        ):
            return answer
    return None


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
            requires_approval=False,
        )

    if kind == "question":
        answer = _answer_for(profile, incoming)
        if answer:
            return ReplyPlan(
                kind=kind,
                body=f"{salutation}\n\n{answer}\n\nLet me know if you need anything else from me.",
                requires_approval=False,
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

    return ReplyPlan(
        kind=kind,
        body=(
            f"{salutation}\n\nThank you for reaching out about {role}. "
            "I am interested and would be happy to talk. Please let me know the next steps."
        ),
        requires_approval=False,
    )
