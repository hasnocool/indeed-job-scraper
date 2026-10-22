"""Write a resume as a Word document.

The output mirrors the layout of the source documents: a large coloured
name, a teal headline, teal section headings, a right-aligned job period and
indented bullets. The content comes from the model, so every format renders
the same resume.
"""

from __future__ import annotations

from pathlib import Path

import docx
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Pt, RGBColor

from .layout import (
    HEADING_EDUCATION,
    HEADING_EXPERIENCE,
    HEADING_SKILLS,
    HEADING_SUMMARY,
)
from .model import Resume

#: The colours of the document.
INK = RGBColor(0x16, 0x32, 0x4F)
BODY = RGBColor(0x26, 0x32, 0x38)
MUTED = RGBColor(0x5C, 0x68, 0x70)
ACCENT = RGBColor(0x17, 0x7E, 0x89)

#: The font sizes of the document, in points.
SIZE_NAME = 25.0
SIZE_HEADLINE = 10.5
SIZE_HEADING = 10.5
SIZE_JOB = 9.5
SIZE_META = 8.0
SIZE_BODY = 9.0
SIZE_BULLET = 9.0

#: The tab stop the job period is aligned to, in twips.
PERIOD_TAB = 9360


def _heading(document: docx.document.Document, text: str) -> None:
    """Write a section heading."""
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(SIZE_HEADING)
    run.font.color.rgb = ACCENT
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(4)


def _body(document: docx.document.Document, text: str) -> None:
    """Write a paragraph of body text."""
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.size = Pt(SIZE_BODY)
    run.font.color.rgb = BODY
    paragraph.paragraph_format.space_after = Pt(6)


def _bullet(document: docx.document.Document, text: str) -> None:
    """Write one bullet line."""
    paragraph = document.add_paragraph(style="List Bullet")
    run = paragraph.add_run(text)
    run.font.size = Pt(SIZE_BULLET)
    run.font.color.rgb = BODY
    paragraph.paragraph_format.space_after = Pt(2)


def _job_header(document: docx.document.Document, company: str, title: str) -> None:
    """Write the company and role line of a job."""
    paragraph = document.add_paragraph()
    company_run = paragraph.add_run(company)
    company_run.bold = True
    company_run.font.size = Pt(SIZE_JOB)
    company_run.font.color.rgb = INK
    if title:
        title_run = paragraph.add_run(f"  |  {title}")
        title_run.font.size = Pt(SIZE_META)
        title_run.font.color.rgb = BODY
    paragraph.paragraph_format.space_before = Pt(8)
    paragraph.paragraph_format.space_after = Pt(0)


def _job_meta(document: docx.document.Document, location: str, period: str) -> None:
    """Write the location and period line of a job.

    The period sits at a right-aligned tab stop, which is how the source
    documents align it against the right margin.
    """
    paragraph = document.add_paragraph()
    tabs = paragraph.paragraph_format.tab_stops
    tabs.add_tab_stop(PERIOD_TAB, WD_TAB_ALIGNMENT.RIGHT)
    if location:
        location_run = paragraph.add_run(location)
        location_run.font.size = Pt(SIZE_META)
        location_run.font.color.rgb = MUTED
    if period:
        paragraph.add_run("\t")
        period_run = paragraph.add_run(period)
        period_run.bold = True
        period_run.font.size = Pt(SIZE_META)
        period_run.font.color.rgb = ACCENT
    paragraph.paragraph_format.space_after = Pt(2)


def _education(document: docx.document.Document, parts: tuple[str, ...]) -> None:
    """Write one education entry."""
    paragraph = document.add_paragraph()
    for index, part in enumerate(parts):
        if not part:
            continue
        run = paragraph.add_run(part if index == 0 else f"  |  {part}")
        if index == 0:
            run.bold = True
            run.font.size = Pt(SIZE_META)
            run.font.color.rgb = INK
        else:
            run.font.size = Pt(SIZE_META)
            run.font.color.rgb = BODY
    paragraph.paragraph_format.space_after = Pt(2)


def render_docx(resume: Resume, path: Path) -> Path:
    """Write the resume as a Word document and return the path written."""
    document = docx.Document()

    name_paragraph = document.add_paragraph()
    name_run = name_paragraph.add_run(resume.name)
    name_run.bold = True
    name_run.font.size = Pt(SIZE_NAME)
    name_run.font.color.rgb = INK
    name_paragraph.paragraph_format.space_after = Pt(0)

    if resume.headline:
        headline_paragraph = document.add_paragraph()
        headline_run = headline_paragraph.add_run(resume.headline)
        headline_run.bold = True
        headline_run.font.size = Pt(SIZE_HEADLINE)
        headline_run.font.color.rgb = ACCENT
        headline_paragraph.paragraph_format.space_after = Pt(0)

    contact_parts = [
        resume.contact.location,
        resume.contact.phone,
        resume.contact.email,
    ]
    while contact_parts and not contact_parts[-1]:
        contact_parts.pop()
    if contact_parts:
        contact_paragraph = document.add_paragraph()
        contact_run = contact_paragraph.add_run("   |   ".join(contact_parts))
        contact_run.font.size = Pt(SIZE_META)
        contact_run.font.color.rgb = MUTED
        contact_paragraph.paragraph_format.space_after = Pt(0)

    if resume.summary:
        _heading(document, HEADING_SUMMARY)
        _body(document, resume.summary)

    if resume.skills:
        _heading(document, HEADING_SKILLS)
        for group in resume.skills:
            if group.label:
                paragraph = document.add_paragraph()
                label_run = paragraph.add_run(f"{group.label}: ")
                label_run.bold = True
                label_run.font.size = Pt(SIZE_META)
                label_run.font.color.rgb = INK
                items_run = paragraph.add_run("; ".join(group.items))
                items_run.font.size = Pt(SIZE_META)
                items_run.font.color.rgb = BODY
                paragraph.paragraph_format.space_after = Pt(2)
                continue
            for item in group.items:
                _bullet(document, item)

    if resume.experience:
        _heading(document, HEADING_EXPERIENCE)
        for job in resume.experience:
            _job_header(document, job.company, job.title)
            _job_meta(document, job.location, job.period)
            for bullet in job.bullets:
                _bullet(document, bullet)

    if resume.education:
        _heading(document, HEADING_EDUCATION)
        for entry in resume.education:
            parts = [entry.institution, entry.credential, entry.location, entry.year]
            while parts and not parts[-1]:
                parts.pop()
            _education(document, tuple(parts))

    if resume.footer:
        paragraph = document.add_paragraph()
        run = paragraph.add_run(resume.footer)
        run.font.size = Pt(SIZE_META)
        run.font.color.rgb = MUTED

    document.save(str(path))
    return path
