"""Errors raised by the resume converters."""

from __future__ import annotations

from pathlib import Path


class ResumeError(Exception):
    """Base class for every resume conversion failure."""


class UnsupportedFormatError(ResumeError):
    """The file extension is not a format this tool knows."""

    def __init__(self, path: Path, known: tuple[str, ...]) -> None:
        self.path = path
        self.known = known
        super().__init__(
            f"{path.suffix or '(no extension)'} is not a resume format. "
            f"Known formats: {', '.join(known)}."
        )


class ParseError(ResumeError):
    """A resume file could not be read into the model."""

    def __init__(self, source: Path | None, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"Could not read {source or 'the resume'}: {reason}")


class FormatError(ResumeError):
    """A resume file is structurally wrong for its format."""

    def __init__(self, source: Path | None, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"{source or 'the resume'} is not valid: {reason}")
