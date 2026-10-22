"""Type definitions for the apply subpackage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: Every status the ledger actually writes. The narrow four-state literal this
#: replaced was already out of date: the flow has always written "submitting"
#: and "dry_run" as well, and nothing checked the annotation.
ApplyStatus = Literal[
    "reserved",
    "submitting",
    "submitted",
    "unconfirmed",
    "blocked",
    "failed",
    "dry_run",
]
PortalType = Literal["indeed", "external", "unknown"]


@dataclass(frozen=True, slots=True)
class ApplyData:
    """Personal information used to fill application forms."""

    name: str
    email: str
    phone: str
    resume_path: str
    cover_letter: str = ""
    screening_answers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Outcome of attempting to apply to a single job."""

    jk: str
    title: str
    company: str
    location: str
    url: str
    status: str
    fingerprint: str
    app_id: str
    portal: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SubmitResult:
    """What actually happened when the submit control was clicked.

    ``clicked`` says the control was found and clicked. ``confirmed`` says a
    POSITIVE success signal was observed afterwards - a confirmation element,
    a confirmation title, or a post-submit URL.

    A click without a confirmation is NOT a submission. The old code returned
    True from a fall-through, so a submission that never happened was recorded
    as one, and "submitted" is a terminal, never-retried ledger state.
    """

    clicked: bool
    confirmed: bool
    detail: str = ""