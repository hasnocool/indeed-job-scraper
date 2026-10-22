"""Convert a resume between formats.

Every format parses into the same model and renders back out of it, so any
format converts to any other. The entry points take a path and choose the
codec by extension; :func:`convert_text` works on the content itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

from .docx_read import parse_docx
from .docx_write import render_docx
from .errors import ParseError, UnsupportedFormatError
from .formats import DEFAULT_EXTENSIONS, EXTENSIONS, FORMAT_NAMES, Format
from .markdown import parse_markdown, render_markdown
from .model import Resume
from .reader import parse_text
from .structured import dump_json, dump_toml, dump_yaml, load_json, load_toml, load_yaml
from .text import render_text

__all__ = [
    "DEFAULT_EXTENSIONS",
    "FORMAT_NAMES",
    "Format",
    "convert_file",
    "convert_text",
    "format_of",
    "parse_file",
    "render",
    "write",
]


def format_of(path: Path) -> Format:
    """The format a path names, by its extension."""
    suffix = path.suffix.lower()
    fmt = EXTENSIONS.get(suffix)
    if fmt is None:
        raise UnsupportedFormatError(path, tuple(sorted(EXTENSIONS)))
    return fmt


def _parse_string(text: str, fmt: Format) -> Resume:
    """Read a resume from text in one of the text formats."""
    match fmt:
        case Format.MARKDOWN:
            return parse_markdown(text)
        case Format.TEXT:
            return parse_text(text)
        case Format.JSON:
            return load_json(text)
        case Format.YAML:
            return load_yaml(text)
        case Format.TOML:
            return load_toml(text)
        case Format.DOCX:
            message = "a Word document is read from a file, not from text"
            raise ParseError(None, message)
        case unreachable:
            assert_never(unreachable)


def parse_file(path: Path) -> Resume:
    """Read a resume file into the model.

    The extension picks the codec. A Word file is read from disk; the other
    formats are read as text.
    """
    fmt = format_of(path)
    if not path.is_file():
        raise ParseError(path, "the file does not exist")
    if fmt is Format.DOCX:
        return parse_docx(path)
    return _parse_string(path.read_text(encoding="utf-8"), fmt)


def render(resume: Resume, fmt: Format) -> str:
    """Render the resume in one of the text formats."""
    match fmt:
        case Format.MARKDOWN:
            return render_markdown(resume)
        case Format.TEXT:
            return render_text(resume)
        case Format.JSON:
            return dump_json(resume)
        case Format.YAML:
            return dump_yaml(resume)
        case Format.TOML:
            return dump_toml(resume)
        case Format.DOCX:
            message = "a Word document is written to a file, not to text"
            raise ParseError(None, message)
        case unreachable:
            assert_never(unreachable)


def write(resume: Resume, path: Path) -> Path:
    """Write the resume to a path, choosing the codec by extension."""
    fmt = format_of(path)
    if fmt is Format.DOCX:
        return render_docx(resume, path)
    path.write_text(render(resume, fmt), encoding="utf-8")
    return path


def convert_file(source: Path, target: Path) -> Path:
    """Convert a resume file into another format."""
    return write(parse_file(source), target)


def convert_text(source: str, source_format: str, target_format: str) -> str:
    """Convert a resume held as text from one format to another."""
    resume = _parse_string(source, Format(source_format))
    return render(resume, Format(target_format))
