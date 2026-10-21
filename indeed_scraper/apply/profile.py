"""Profile management for apply data."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, field_validator

from indeed_scraper.apply.exceptions import ProfileNotFoundError

from .types import ApplyData

PROFILE_PATH: Path = Path(os.environ.get("INDEED_PROFILE_PATH") or "~/.config/indeed_scraper/profile.json").expanduser()


class Profile(BaseModel):
    """Applicant profile data."""

    name: str
    email: str
    phone: str
    resume_path: str
    cover_letter: str = ""
    screening_answers: dict[str, str] = {}
    work_authorization: str = ""
    salary_expectations: str = ""
    availability: str = ""
    notice_period: str = ""
    visa_sponsorship: bool = False

    @field_validator("*", mode="after")
    @classmethod
    def ensure_no_fabricated_defaults(cls, v: str) -> str:
        """No field silently fabricates a default; callers must treat '' as MISSING."""
        return v


#: A real resume PDF is far larger than this; anything smaller is a stub.
MIN_RESUME_BYTES = 1024
PDF_MAGIC = b"%PDF"


def validate_resume(path: Path) -> Path:
    """Check that the resume is a real PDF, not a placeholder.

    A stub resume would be uploaded to an employer, so the flow refuses to
    run with one and says exactly what is wrong.
    """
    if not path.is_file():
        raise ProfileNotFoundError(
            f"No resume file at {path}. Put your PDF there, or point resume_path at it."
        )
    size = path.stat().st_size
    if size < MIN_RESUME_BYTES:
        raise ProfileNotFoundError(
            f"The resume at {path} is only {size} bytes - that is a placeholder, not a "
            f"resume. Replace it with your real PDF (at least {MIN_RESUME_BYTES} bytes)."
        )
    with path.open("rb") as handle:
        if not handle.read(len(PDF_MAGIC)).startswith(PDF_MAGIC):
            raise ProfileNotFoundError(
                f"The resume at {path} is not a PDF (no %PDF header)."
            )
    return path


def profile_template() -> Profile:
    """A profile skeleton with the values the operator must fill in."""
    return Profile(
        name="",
        email="",
        phone="",
        resume_path=str(Path(os.path.expanduser("~/.config/indeed_scraper/resume.pdf"))),
    )


def load_profile(path: Path | None = None) -> Profile:
    """Load a Profile from a JSON file.

    Raises ProfileNotFoundError if the file does not exist.
    Raises on invalid JSON.
    """
    p = path or PROFILE_PATH
    expanded = p if p.is_absolute() else Path(os.environ.get("INDEED_PROFILE_PATH", "~/.config/indeed_scraper/profile.json")).expanduser()
    if not expanded.exists():
        raise ProfileNotFoundError(
            f"Profile not found at {expanded}. "
            "Create the file with the required fields (name, email, phone, resume_path)."
        )
    mode = expanded.stat().st_mode & 0o077
    if mode:
        raise ProfileNotFoundError(
            f"Profile file {expanded} is readable by others (mode {mode:o}). "
            f"Run: chmod 600 {expanded}"
        )
    try:
        data = json.loads(expanded.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileNotFoundError(
            f"Invalid JSON in profile file {expanded}: {exc}"
        ) from exc
    profile = Profile(**data)
    validate_resume(Path(profile.resume_path).expanduser())
    return profile


def save_profile(profile: Profile, path: Path | None = None) -> Path:
    """Save a Profile to a JSON file atomically.

    Writes to a temp file in the same directory, then os.replace.
    Sets the file mode to 0600 and the parent directory mode to 0700.
    Creates the parent directory if it does not exist.
    Returns the path written to.
    """
    p = path or PROFILE_PATH
    expanded = p if p.is_absolute() else Path(os.environ.get("INDEED_PROFILE_PATH", "~/.config/indeed_scraper/profile.json")).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    expanded.parent.chmod(0o700)
    tmp = expanded.with_suffix(".tmp")
    try:
        tmp.write_text(profile.model_dump_json(), encoding="utf-8")
        tmp.chmod(0o600)
        os.replace(tmp, expanded)
    finally:
        if tmp.exists():
            tmp.unlink()
    return expanded


def apply_data(profile: Profile) -> ApplyData:
    """Map a Profile to the ApplyData shape the form filler consumes.

    The mapping is an in-memory convenience only: the values never reach the
    ledger or a draft file, which carry field NAMES instead.
    """
    return ApplyData(
        name=profile.name,
        email=profile.email,
        phone=profile.phone,
        resume_path=profile.resume_path,
        cover_letter=profile.cover_letter,
        screening_answers=profile.screening_answers,
    )
