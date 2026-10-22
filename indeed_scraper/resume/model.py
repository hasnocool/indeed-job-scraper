"""The canonical resume shape.

Every format - DOCX, Markdown, plain text, JSON, YAML and TOML - parses into
this one model and renders back out of it. The model is the contract between
the codecs, so it stays small and explicit rather than clever: a codec that
cannot represent a field loses it, and a field nobody writes is dead weight.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Contact(BaseModel):
    """How the applicant can be reached."""

    model_config = ConfigDict(frozen=True)

    location: str = ""
    phone: str = ""
    email: str = ""


class SkillGroup(BaseModel):
    """A group of skill phrases under one optional label.

    ``label`` is empty for the two-column skill matrix in the source
    documents, where the phrases stand on their own with no heading.
    """

    model_config = ConfigDict(frozen=True)

    label: str = ""
    items: tuple[str, ...] = ()


class Experience(BaseModel):
    """One job: who, what, where, when, and what was done there."""

    model_config = ConfigDict(frozen=True)

    company: str
    title: str = ""
    location: str = ""
    period: str = ""
    bullets: tuple[str, ...] = ()


class Education(BaseModel):
    """One credential."""

    model_config = ConfigDict(frozen=True)

    institution: str
    credential: str = ""
    location: str = ""
    year: str = ""


class Resume(BaseModel):
    """A whole resume."""

    model_config = ConfigDict(frozen=True)

    name: str
    headline: str = ""
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    skills: tuple[SkillGroup, ...] = ()
    experience: tuple[Experience, ...] = ()
    education: tuple[Education, ...] = ()
    footer: str = ""
