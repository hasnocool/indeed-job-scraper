"""The plain-text resume codec.

Plain text is the text format with no decoration: the same headings and
bullets as the other formats, written out as they stand. Reading it is the
work of :mod:`indeed_scraper.resume.reader`, which the Markdown codec shares.
"""

from __future__ import annotations

from .layout import (
    HEADING_EDUCATION,
    HEADING_EXPERIENCE,
    HEADING_SKILLS,
    HEADING_SUMMARY,
    RULE,
    contact_line,
    education_line,
    job_header,
    job_meta,
    skill_line,
)
from .model import Resume
from .reader import parse_text

__all__ = ["parse_text", "render_text"]


def _skill_lines(resume: Resume) -> list[str]:
    """Render the skill groups as bullet lines.

    A labelled group is one bullet; an unlabelled group is one bullet per
    item, which is what makes a two-column skill matrix readable.
    """
    lines: list[str] = []
    for group in resume.skills:
        if group.label:
            lines.append(f"- {skill_line(group)}")
            continue
        lines.extend(f"- {item}" for item in group.items)
    return lines


def render_text(resume: Resume) -> str:
    """Render the resume as plain text."""
    out: list[str] = [resume.name]
    if resume.headline:
        out.append(resume.headline)
    contact = contact_line(resume.contact)
    if contact:
        out.append(contact)
    if resume.summary:
        out.extend(["", HEADING_SUMMARY, "", resume.summary])
    if resume.skills:
        out.extend(["", HEADING_SKILLS, ""])
        out.extend(_skill_lines(resume))
    if resume.experience:
        out.extend(["", HEADING_EXPERIENCE, ""])
        for job in resume.experience:
            out.append(job_header(job))
            out.append(job_meta(job))
            out.append("")
            out.extend(f"- {bullet}" for bullet in job.bullets)
            out.append("")
    if resume.education:
        out.extend(["", HEADING_EDUCATION, ""])
        out.extend(f"- {education_line(entry)}" for entry in resume.education)
    if resume.footer:
        out.extend(["", RULE, resume.footer])
    return "\n".join(out).rstrip() + "\n"
