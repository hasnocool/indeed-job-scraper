"""The shared line vocabulary of the text-shaped resume formats.

Markdown and plain text describe the same resume with different decoration, so
the *content* rules live here once: how a contact line, a skill line, a job
header, a job meta line and an education entry are written and read back.
Both text codecs use these helpers, which is what keeps a round trip
lossless no matter which of the two a file was written in.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from .model import Contact, Education, Experience, SkillGroup


class Section(StrEnum):
    """The sections a resume can have."""

    SUMMARY = "summary"
    SKILLS = "skills"
    EXPERIENCE = "experience"
    EDUCATION = "education"


#: The separator both text formats use between fields on one line.
SEP: Final = " | "

#: A separator with any amount of padding around it, as it appears in
#: documents that align their columns with tabs, wide spacing or a pipe.
SEP_RE: Final = re.compile(r"\t+|\s*\|\s*")

#: A year range, a bare year or a range ending in "Present".
PERIOD_RE: Final = re.compile(
    r"^(?:(?:19|20)\d{2}\s*[-–—]\s*(?:(?:19|20)\d{2}|Present|Current|Now|Today)"
    r"|(?:19|20)\d{2}"
    r"|Present|Current)$"
)

#: The separator between the items of one skill group.
ITEM_SEP: Final = "; "

#: A bullet at the start of a line.
BULLET_RE: Final = re.compile(r"^(?:[-*•–])\s+")

#: The horizontal rule that introduces the trailing note of a resume.
RULE: Final = "---"

#: The section names the text formats write.
HEADING_SUMMARY: Final = "PROFESSIONAL SUMMARY"
HEADING_SKILLS: Final = "CORE TECHNICAL SKILLS"
HEADING_EXPERIENCE: Final = "PROFESSIONAL EXPERIENCE"
HEADING_EDUCATION: Final = "EDUCATION & TRAINING"

#: Every heading spelling that maps onto a section.
SECTION_LOOKUP: Final[dict[str, Section]] = {
    "PROFESSIONAL SUMMARY": Section.SUMMARY,
    "SUMMARY": Section.SUMMARY,
    "CORE TECHNICAL SKILLS": Section.SKILLS,
    "TECHNICAL SKILLS": Section.SKILLS,
    "SKILLS": Section.SKILLS,
    "PROFESSIONAL EXPERIENCE": Section.EXPERIENCE,
    "WORK EXPERIENCE": Section.EXPERIENCE,
    "EXPERIENCE": Section.EXPERIENCE,
    "EDUCATION & TRAINING": Section.EDUCATION,
    "EDUCATION AND TRAINING": Section.EDUCATION,
    "EDUCATION": Section.EDUCATION,
}


def split_fields(line: str) -> list[str]:
    """Split a line on the field separator and drop the empty fields."""
    return [part.strip() for part in SEP_RE.split(line) if part.strip()]


def is_bullet(line: str) -> bool:
    """Is this line a bullet item?"""
    return bool(BULLET_RE.match(line.strip()))


def strip_bullet(line: str) -> str:
    """Remove a leading bullet marker from a line."""
    return BULLET_RE.sub("", line.strip(), count=1)


def section_key(line: str) -> Section | None:
    """The section a heading line names, or None when it names none.

    A "(CONTINUED)" suffix names the same section as the heading it repeats,
    so a resume split across pages keeps one section.
    """
    text = re.sub(r"\s+", " ", line.strip()).upper()
    if text.endswith("(CONTINUED)"):
        text = text[: -len("(CONTINUED)")].strip()
    return SECTION_LOOKUP.get(text)


def contact_line(contact: Contact) -> str:
    """Render the contact line: location, phone and email.

    Empty trailing fields are dropped, so the common case stays short.
    """
    parts = [contact.location, contact.phone, contact.email]
    while parts and not parts[-1]:
        parts.pop()
    return SEP.join(parts)


def parse_contact(line: str) -> Contact:
    """Read a contact line back.

    The email is recognised by its ``@`` so a missing phone never shifts the
    email into the phone slot.
    """
    parts = split_fields(line)
    if not parts:
        return Contact()
    email = ""
    for index, part in enumerate(parts):
        if "@" in part:
            email = parts.pop(index)
            break
    if not parts:
        return Contact(email=email)
    phone = parts.pop() if email else parts.pop() if len(parts) > 1 else ""
    return Contact(location=SEP.join(parts), phone=phone, email=email)


def skill_line(group: SkillGroup) -> str:
    """Render one skill group as ``Label: item; item``."""
    items = ITEM_SEP.join(group.items)
    if not group.label:
        return items
    return f"{group.label}: {items}"


def parse_skill(line: str) -> SkillGroup:
    """Read one skill group back.

    The label is whatever precedes the first colon; a line with no colon is
    an unlabelled group.
    """
    label, separator, rest = line.partition(":")
    if not separator:
        items = (item.strip() for item in line.split(";") if item.strip())
        return SkillGroup(items=tuple(items))
    items = tuple(item.strip() for item in rest.split(";") if item.strip())
    return SkillGroup(label=label.strip(), items=items)


def job_header(experience: Experience) -> str:
    """Render the job title line: company and role."""
    if not experience.title:
        return experience.company
    return f"{experience.company}{SEP}{experience.title}"


def parse_job_header(line: str) -> Experience:
    """Read a job title line back into an experience entry."""
    parts = split_fields(line)
    if len(parts) == 1:
        return Experience(company=parts[0])
    return Experience(company=parts[0], title=SEP.join(parts[1:]))


def job_meta(experience: Experience) -> str:
    """Render the job location and period line."""
    if not experience.location:
        return experience.period
    if not experience.period:
        return experience.location
    return f"{experience.location}{SEP}{experience.period}"


def parse_job_meta(line: str) -> tuple[str, str]:
    """Read a job location and period line back as ``(location, period)``."""
    parts = split_fields(line)
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], SEP.join(parts[1:])


def is_period_line(line: str) -> bool:
    """Is this line the location and period line of a job?

    A period always ends the line, so a line whose last field is a year or
    a year range is the meta line. This is what tells a job's meta line
    apart from the next job's title line.
    """
    parts = split_fields(line)
    if not parts:
        return False
    return bool(PERIOD_RE.match(parts[-1]))


def education_line(education: Education) -> str:
    """Render an education entry.

    The fields are positional - institution, credential, location, year - and
    trailing empty fields are dropped, which is what makes a two, three or
    four part line unambiguous when it is read back.
    """
    parts = [
        education.institution,
        education.credential,
        education.location,
        education.year,
    ]
    while parts and not parts[-1]:
        parts.pop()
    return SEP.join(parts)


def _looks_like_year(text: str) -> bool:
    """Is this field a year rather than a place?"""
    return bool(re.fullmatch(r"(?:19|20)\d{2}", text.strip()))


def parse_education(line: str) -> Education:
    """Read an education entry back.

    The number of fields decides the shape: two parts is institution and
    credential, three adds either the year or the location, four adds both.
    """
    parts = split_fields(line)
    if len(parts) >= 4:
        return Education(
            institution=parts[0],
            credential=parts[1],
            location=parts[2],
            year=parts[3],
        )
    if len(parts) == 3:
        year = parts[2] if _looks_like_year(parts[2]) else ""
        location = "" if year else parts[2]
        return Education(
            institution=parts[0],
            credential=parts[1],
            location=location,
            year=year,
        )
    if len(parts) == 2:
        return Education(institution=parts[0], credential=parts[1])
    return Education(institution=parts[0])
