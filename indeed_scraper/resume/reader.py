"""Read the canonical lines of a resume into the model.

This is the shared engine of the text-shaped formats. It cuts a document into
its header, its sections and its trailing note, then reads each section with
the rules that format uses. :mod:`indeed_scraper.resume.markdown` normalises
Markdown into the same lines before handing them over, which is what keeps a
Markdown file and a plain-text file of one resume interchangeable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import assert_never

from .errors import FormatError
from .layout import (
    RULE,
    Section,
    is_bullet,
    is_period_line,
    parse_contact,
    parse_education,
    parse_job_header,
    parse_job_meta,
    parse_skill,
    section_key,
    strip_bullet,
)
from .model import Contact, Education, Experience, Resume, SkillGroup


def _split_document(
    lines: Sequence[str],
) -> tuple[list[str], list[tuple[Section, list[str]]], list[str]]:
    """Cut a document into its header, its sections and its trailing note.

    The header is everything before the first heading, the sections are the
    runs between headings, and the note is what follows the horizontal rule.
    """
    note: list[str] = []
    body: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() == RULE:
            note.extend(item.strip() for item in lines[index + 1 :] if item.strip())
            break
        body.append(line)

    header: list[str] = []
    sections: list[tuple[Section, list[str]]] = []
    by_key: dict[Section, list[str]] = {}
    current: list[str] | None = None
    for line in body:
        key = section_key(line)
        if key is not None:
            if key not in by_key:
                by_key[key] = []
                sections.append((key, by_key[key]))
            current = by_key[key]
            continue
        if current is None:
            header.append(line)
        else:
            current.append(line)
    return header, sections, note


def _parse_header(header: Sequence[str]) -> tuple[str, str, Contact]:
    """Read the name, the headline and the contact out of the header block.

    The block holds the name, then the headline, then the contact line. A
    resume with no headline leaves the block one line short, which is how the
    reader tells the two apart.
    """
    fields = [line.strip() for line in header if line.strip()]
    if not fields:
        raise FormatError(None, "the resume has no name")
    name = fields[0]
    if len(fields) >= 3:
        return name, fields[1], parse_contact(fields[-1])
    if len(fields) == 2:
        return name, "", parse_contact(fields[1])
    return name, "", Contact()


def _parse_summary(lines: Sequence[str]) -> str:
    """Read the summary section: its paragraphs joined by a blank line."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(text)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def _parse_skills(lines: Sequence[str]) -> list[SkillGroup]:
    """Read the skills section.

    A line with a colon is a labelled group; every other line is one item,
    and consecutive items form a single unlabelled group.
    """
    entries: list[tuple[bool, SkillGroup]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if is_bullet(text):
            text = strip_bullet(text)
        if ":" in text:
            entries.append((True, parse_skill(text)))
        else:
            entries.append((False, SkillGroup(items=(text,))))

    groups: list[SkillGroup] = []
    loose: list[str] = []
    for labelled, group in entries:
        if not labelled:
            loose.extend(group.items)
            continue
        if loose:
            groups.append(SkillGroup(items=tuple(loose)))
            loose = []
        groups.append(group)
    if loose:
        groups.append(SkillGroup(items=tuple(loose)))
    return groups


def _parse_experience(lines: Sequence[str]) -> list[Experience]:
    """Read the experience section.

    A job is a title line, then an optional location and period line, then
    its bullets. The meta line is recognised by its period rather than by
    its position, so a job that has no location still reads correctly.
    """
    jobs: list[Experience] = []
    index = 0
    count = len(lines)
    while index < count:
        header_line = lines[index].strip()
        if not header_line:
            index += 1
            continue
        header = parse_job_header(strip_bullet(header_line))
        index += 1
        location = ""
        period = ""
        probe = index
        while probe < count and not lines[probe].strip():
            probe += 1
        if probe < count:
            candidate = lines[probe].strip()
            if not is_bullet(candidate) and is_period_line(candidate):
                location, period = parse_job_meta(candidate)
                index = probe + 1
        bullets: list[str] = []
        while index < count:
            candidate = lines[index].strip()
            if not candidate:
                index += 1
                continue
            if not is_bullet(candidate):
                break
            bullets.append(strip_bullet(candidate))
            index += 1
        jobs.append(
            Experience(
                company=header.company,
                title=header.title,
                location=location,
                period=period,
                bullets=tuple(bullets),
            )
        )
    return jobs


def _parse_education(lines: Sequence[str]) -> tuple[list[Education], list[str]]:
    """Read the education section and whatever note follows it.

    An education entry always has a separator; a line without one is the
    trailing note of the resume.
    """
    entries: list[Education] = []
    note: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if is_bullet(text):
            text = strip_bullet(text)
        if "|" in text:
            entries.append(parse_education(text))
        else:
            note.append(text)
    return entries, note


def parse_lines(lines: Sequence[str]) -> Resume:
    """Read a resume out of the lines of a text-shaped document."""
    header, sections, note = _split_document(lines)
    name, headline, contact = _parse_header(header)
    summary = ""
    skills: list[SkillGroup] = []
    experience: list[Experience] = []
    education: list[Education] = []
    for key, section_lines in sections:
        match key:
            case Section.SUMMARY:
                summary = _parse_summary(section_lines)
            case Section.SKILLS:
                skills = _parse_skills(section_lines)
            case Section.EXPERIENCE:
                experience = _parse_experience(section_lines)
            case Section.EDUCATION:
                entries, trailing = _parse_education(section_lines)
                education = entries
                note.extend(trailing)
            case unreachable:
                assert_never(unreachable)
    return Resume(
        name=name,
        headline=headline,
        contact=contact,
        summary=summary,
        skills=tuple(skills),
        experience=tuple(experience),
        education=tuple(education),
        footer="\n".join(note),
    )


def parse_text(text: str) -> Resume:
    """Read a resume from plain text."""
    return parse_lines(text.splitlines())
