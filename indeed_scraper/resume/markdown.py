"""The Markdown resume codec.

Markdown is the text format with decoration: headings for the name and the
sections, bullets for the items. The reading side normalises Markdown back
into the plain lines the shared engine understands, so a Markdown file and a
plain-text file of the same resume produce the same model.
"""

from __future__ import annotations

import re

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
from .reader import parse_lines

#: A Markdown heading of any level.
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")

#: A Markdown bullet or numbered item.
LIST_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+(.*)$")

#: A Markdown horizontal rule.
HR_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")

#: The emphasis markers a line may carry.
EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1", re.DOTALL)

#: The section heading each section is written under.
SECTION_HEADINGS = (
    (HEADING_SUMMARY, "summary"),
    (HEADING_SKILLS, "skills"),
    (HEADING_EXPERIENCE, "experience"),
    (HEADING_EDUCATION, "education"),
)


def _to_plain_lines(markdown: str) -> list[str]:
    """Strip the Markdown decoration and keep the content lines.

    A heading becomes the bare heading text, a list item becomes a plain
    bullet, and a horizontal rule stays a rule so the trailing note keeps
    its own section.
    """
    lines: list[str] = []
    in_fence = False
    for raw in markdown.splitlines():
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            lines.append(raw)
            continue
        heading = HEADING_RE.match(raw)
        if heading:
            lines.append(heading.group(2))
            continue
        item = LIST_RE.match(raw)
        if item:
            lines.append(f"- {_strip_emphasis(item.group(1))}")
            continue
        if HR_RE.match(raw):
            lines.append(RULE)
            continue
        lines.append(_strip_emphasis(raw))
    return lines


def _strip_emphasis(text: str) -> str:
    """Remove the emphasis markers from a line of Markdown."""
    return EMPHASIS_RE.sub(r"\2", text).strip()


def parse_markdown(markdown: str) -> Resume:
    """Read a resume from Markdown."""
    return parse_lines(_to_plain_lines(markdown))


def _skill_lines(resume: Resume) -> list[str]:
    """Render the skill groups as Markdown bullets.

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


def render_markdown(resume: Resume) -> str:
    """Render the resume as Markdown."""
    out: list[str] = [f"# {resume.name}"]
    if resume.headline:
        out.extend(["", f"**{resume.headline}**"])
    contact = contact_line(resume.contact)
    if contact:
        out.extend(["", contact])
    if resume.summary:
        out.extend(["", f"## {HEADING_SUMMARY}", "", resume.summary])
    if resume.skills:
        out.extend(["", f"## {HEADING_SKILLS}", ""])
        out.extend(_skill_lines(resume))
    if resume.experience:
        out.extend(["", f"## {HEADING_EXPERIENCE}", ""])
        for job in resume.experience:
            out.append(f"### {job_header(job)}")
            out.append("")
            out.append(job_meta(job))
            out.append("")
            out.extend(f"- {bullet}" for bullet in job.bullets)
            out.append("")
    if resume.education:
        out.extend(["", f"## {HEADING_EDUCATION}", ""])
        out.extend(f"- {education_line(entry)}" for entry in resume.education)
    if resume.footer:
        out.extend(["", RULE, "", resume.footer])
    return "\n".join(out).rstrip() + "\n"
