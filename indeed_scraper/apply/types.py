"""Type definitions for the apply subpackage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ApplyStatus = Literal["reserved", "submitted", "blocked", "failed"]
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