"""The resume formats this tool knows.

A format is one name with several spellings on disk: ``.yaml`` and ``.yml``
are the same format, and ``.md`` and ``.markdown`` are the same format. The
enum keeps those spellings from spreading through the code, so a format is
matched on once and never spelled out again.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Format(StrEnum):
    """One resume format."""

    DOCX = "docx"
    MARKDOWN = "markdown"
    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    TOML = "toml"


#: The extension each format is written with by default.
DEFAULT_EXTENSIONS: Final[dict[Format, str]] = {
    Format.DOCX: ".docx",
    Format.MARKDOWN: ".md",
    Format.TEXT: ".txt",
    Format.JSON: ".json",
    Format.YAML: ".yaml",
    Format.TOML: ".toml",
}

#: Every extension, and the format it names.
EXTENSIONS: Final[dict[str, Format]] = {
    ".docx": Format.DOCX,
    ".md": Format.MARKDOWN,
    ".markdown": Format.MARKDOWN,
    ".txt": Format.TEXT,
    ".text": Format.TEXT,
    ".json": Format.JSON,
    ".yaml": Format.YAML,
    ".yml": Format.YAML,
    ".toml": Format.TOML,
}

#: The format names, in the order the table shows them.
FORMAT_NAMES: Final[tuple[str, ...]] = tuple(fmt.value for fmt in Format)
