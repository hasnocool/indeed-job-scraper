"""Resume conversion between DOCX, Markdown, text, JSON, YAML and TOML.

The public surface is deliberately small: :func:`convert_file` for files,
:func:`convert_text` for strings, and :func:`parse_file` plus :func:`write`
for the two halves when a caller needs them separately.
"""

from __future__ import annotations

from .convert import (
    convert_file,
    convert_text,
    format_of,
    parse_file,
    render,
    write,
)
from .errors import (
    FormatError,
    ParseError,
    ResumeError,
    UnsupportedFormatError,
)
from .formats import DEFAULT_EXTENSIONS, FORMAT_NAMES, Format
from .model import Contact, Education, Experience, Resume, SkillGroup

__all__ = [
    "DEFAULT_EXTENSIONS",
    "FORMAT_NAMES",
    "Contact",
    "Education",
    "Experience",
    "Format",
    "FormatError",
    "ParseError",
    "Resume",
    "ResumeError",
    "SkillGroup",
    "UnsupportedFormatError",
    "convert_file",
    "convert_text",
    "format_of",
    "parse_file",
    "render",
    "write",
]
