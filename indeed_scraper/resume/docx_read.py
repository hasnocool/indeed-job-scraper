"""Read a Word document into the plain lines of a resume.

A Word file is a sequence of paragraphs and tables with styling on top.
This module strips the styling and leaves the content in the canonical line
form, so the shared engine in :mod:`indeed_scraper.resume.reader` does the
actual reading. That is what lets a DOCX, a Markdown file and a plain-text
file of the same resume produce the same model.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

import docx
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph

from .errors import ParseError
from .layout import Section, is_bullet, section_key, strip_bullet
from .model import Resume
from .reader import parse_lines

#: The style names Word applies to the bullet lines of these documents.
BULLET_STYLES = frozenset({"Resume Bullet", "List Bullet", "List Paragraph"})

#: The separator between the two halves of a skill-matrix cell.
CELL_SEP = "•"


def _blocks(document: DocumentObject) -> list[Paragraph | Table]:
    """Every paragraph and table of the document, in reading order."""
    return list(document.iter_inner_content())


def _style_name(paragraph: Paragraph) -> str:
    """The name of the paragraph's style, or an empty string."""
    style = paragraph.style
    return style.name if style is not None else ""


def _is_bullet_paragraph(paragraph: Paragraph) -> bool:
    """Is this paragraph one of the bullet lines?"""
    if _style_name(paragraph) in BULLET_STYLES:
        return True
    return is_bullet(paragraph.text)


def _bullet_text(paragraph: Paragraph) -> str:
    """The text of a bullet paragraph without its marker."""
    if _style_name(paragraph) in BULLET_STYLES:
        return paragraph.text.strip().lstrip("•").strip()
    return strip_bullet(paragraph.text)


def _labelled_skill(paragraph: Paragraph) -> str | None:
    """The canonical skill line when the paragraph leads with a bold label.

    These documents label a skill group by making the first run bold and
    ending it with a colon; the rest of the paragraph is the item list.
    """
    runs = [run for run in paragraph.runs if run.text.strip()]
    if not runs:
        return None
    first = runs[0]
    if not first.bold or not first.text.rstrip().endswith(":"):
        return None
    label = first.text.strip().rstrip(":").strip()
    rest = "".join(run.text for run in runs[1:]).strip()
    if not label or not rest:
        return None
    items = _split_items(rest)
    return f"{label}: {'; '.join(items)}"


def _split_items(text: str) -> list[str]:
    """Split a skill item list on its separator.

    A group written with semicolons keeps them; one written as a comma list
    is split on the commas instead.
    """
    if ";" in text:
        parts = text.split(";")
    else:
        parts = text.split(",")
    return [part.strip() for part in parts if part.strip()]


def _table_lines(table: Table) -> list[str]:
    """The skill items of a two-column skill matrix, one per line."""
    lines: list[str] = []
    for row in table.rows:
        for cell in row.cells:
            for item in cell.text.split(CELL_SEP):
                text = item.strip()
                if text:
                    lines.append(f"- {text}")
    return lines


def docx_to_lines(path: Path) -> list[str]:
    """Read a Word document into the canonical lines of a resume."""
    try:
        document = docx.Document(str(path))
    except (OSError, ValueError, KeyError) as error:
        reason = f"the Word file could not be opened ({error})"
        raise ParseError(path, reason) from error

    lines: list[str] = []
    section: Section | None = None
    for block in _blocks(document):
        match block:
            case Paragraph():
                text = block.text.strip()
                if not text:
                    continue
                key = section_key(text)
                if key is not None:
                    section = key
                    lines.append(text)
                    continue
                if section is Section.SKILLS:
                    labelled = _labelled_skill(block)
                    if labelled is not None:
                        lines.append(labelled)
                        continue
                if _is_bullet_paragraph(block):
                    lines.append(f"- {_bullet_text(block)}")
                    continue
                lines.append(text)
            case Table():
                lines.extend(_table_lines(block))
            case unreachable:
                assert_never(unreachable)
    return lines


def parse_docx(path: Path) -> Resume:
    """Read a resume from a Word document."""
    return parse_lines(docx_to_lines(path))
