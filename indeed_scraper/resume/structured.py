"""The structured resume codecs: JSON, YAML and TOML.

These three formats carry the same tree, so they share one dump and one load
per format and differ only in the library used to serialise. Keeping them
together makes the round-trip guarantee obvious: a resume written to any of
the three and read back yields the same model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tomli_w
import tomllib
import yaml

from .errors import FormatError
from .model import Contact, Education, Experience, Resume, SkillGroup


def _to_plain(resume: Resume) -> dict[str, Any]:
    """Flatten the model into plain containers the serialisers accept."""
    return {
        "name": resume.name,
        "headline": resume.headline,
        "contact": {
            "location": resume.contact.location,
            "phone": resume.contact.phone,
            "email": resume.contact.email,
        },
        "summary": resume.summary,
        "skills": [
            {"label": group.label, "items": list(group.items)}
            for group in resume.skills
        ],
        "experience": [
            {
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "period": job.period,
                "bullets": list(job.bullets),
            }
            for job in resume.experience
        ],
        "education": [
            {
                "institution": entry.institution,
                "credential": entry.credential,
                "location": entry.location,
                "year": entry.year,
            }
            for entry in resume.education
        ],
        "footer": resume.footer,
    }


def _from_plain(data: dict[str, Any]) -> Resume:
    """Rebuild the model from plain containers.

    Missing keys are tolerated so a hand-written file in any of the three
    formats still loads; anything present is used as given.
    """
    contact = data.get("contact") or {}
    return Resume(
        name=str(data.get("name", "")),
        headline=str(data.get("headline", "")),
        contact=Contact(
            location=str(contact.get("location", "")),
            phone=str(contact.get("phone", "")),
            email=str(contact.get("email", "")),
        ),
        summary=str(data.get("summary", "")),
        skills=tuple(
            SkillGroup(
                label=str(group.get("label", "")),
                items=tuple(str(item) for item in group.get("items", ())),
            )
            for group in data.get("skills", ())
        ),
        experience=tuple(
            Experience(
                company=str(job.get("company", "")),
                title=str(job.get("title", "")),
                location=str(job.get("location", "")),
                period=str(job.get("period", "")),
                bullets=tuple(str(bullet) for bullet in job.get("bullets", ())),
            )
            for job in data.get("experience", ())
        ),
        education=tuple(
            Education(
                institution=str(entry.get("institution", "")),
                credential=str(entry.get("credential", "")),
                location=str(entry.get("location", "")),
                year=str(entry.get("year", "")),
            )
            for entry in data.get("education", ())
        ),
        footer=str(data.get("footer", "")),
    )


def dump_json(resume: Resume) -> str:
    """Render the resume as JSON."""
    return json.dumps(_to_plain(resume), indent=2, ensure_ascii=False) + "\n"


def load_json(text: str) -> Resume:
    """Read a resume from JSON."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise FormatError(Path("<json>"), str(error)) from error
    return _from_plain(data)


def dump_yaml(resume: Resume) -> str:
    """Render the resume as YAML."""
    return yaml.safe_dump(
        _to_plain(resume),
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


def load_yaml(text: str) -> Resume:
    """Read a resume from YAML."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise FormatError(Path("<yaml>"), str(error)) from error
    return _from_plain(data or {})


def dump_toml(resume: Resume) -> str:
    """Render the resume as TOML.

    TOML requires every scalar key to come before any sub-table key, so the
    sections are emitted in a fixed order rather than in model order.
    """
    plain = _to_plain(resume)
    ordered = {
        "name": plain["name"],
        "headline": plain["headline"],
        "summary": plain["summary"],
        "footer": plain["footer"],
        "contact": plain["contact"],
        "skills": plain["skills"],
        "experience": plain["experience"],
        "education": plain["education"],
    }
    return tomli_w.dumps(ordered)


def load_toml(text: str) -> Resume:
    """Read a resume from TOML."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise FormatError(Path("<toml>"), str(error)) from error
    return _from_plain(data)
