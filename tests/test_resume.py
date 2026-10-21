"""The resume must be a real PDF, never a placeholder.

A stub resume would be uploaded to an employer, so the profile refuses to
load with one and says exactly what is wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indeed_scraper.apply.exceptions import FieldMissingError
from indeed_scraper.apply.profile import (
    MIN_RESUME_BYTES,
    Profile,
    ProfileNotFoundError,
    load_profile,
    save_profile,
    validate_resume,
)


class _StubPage:
    """The smallest page the resume check needs."""

    url = "https://ca.indeed.com/apply/in/test123"


def _pdf(size: int = 2048) -> bytes:
    return b"%PDF-1.4\n" + b"0 " * size


def test_a_real_pdf_passes(tmp_path: Path) -> None:
    path = tmp_path / "resume.pdf"
    path.write_bytes(_pdf())
    assert validate_resume(path) == path


def test_a_missing_resume_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProfileNotFoundError) as error:
        validate_resume(tmp_path / "nope.pdf")
    assert "No resume file" in str(error.value)


def test_a_placeholder_resume_is_refused(tmp_path: Path) -> None:
    """A 58-byte stub is exactly what would be sent to an employer."""
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-1.4\n% PLACEHOLDER resume - replace with your own PDF\n")
    with pytest.raises(ProfileNotFoundError) as error:
        validate_resume(path)
    message = str(error.value)
    assert "placeholder" in message
    assert str(path) in message


def test_a_non_pdf_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"not a pdf at all" * 200)
    with pytest.raises(ProfileNotFoundError) as error:
        validate_resume(path)
    assert "not a PDF" in str(error.value)


def test_the_profile_loads_without_a_usable_resume(tmp_path: Path) -> None:
    """Loading a profile must not require a resume.

    The resume is only needed to APPLY. The messaging path reads the same
    profile, and a recruiter reply does not need a resume file, so the gate
    lives on the apply path, not on the load path.
    """
    stub = tmp_path / "resume.pdf"
    stub.write_bytes(b"%PDF-1.4\n% stub\n")
    profile = Profile(
        name="Test",
        email="t@example.com",
        phone="555",
        resume_path=str(stub),
    )
    path = tmp_path / "profile.json"
    save_profile(profile, path)
    assert load_profile(path).resume_path == str(stub)


def test_the_apply_path_refuses_a_placeholder_resume(tmp_path: Path) -> None:
    """The gate is on the apply path, so no application can slip past it."""
    from indeed_scraper.apply.indeed_form import fill_indeed_form

    stub = tmp_path / "resume.pdf"
    stub.write_bytes(b"%PDF-1.4\n% stub\n")
    profile = Profile(
        name="Test",
        email="t@example.com",
        phone="555",
        resume_path=str(stub),
    )
    with pytest.raises(FieldMissingError) as error:
        fill_indeed_form(_StubPage(), profile)
    assert "placeholder" in str(error.value)


def test_the_profile_loads_with_a_real_resume(tmp_path: Path) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(_pdf())
    profile = Profile(
        name="Test",
        email="t@example.com",
        phone="555",
        resume_path=str(resume),
    )
    path = tmp_path / "profile.json"
    save_profile(profile, path)
    assert load_profile(path).resume_path == str(resume)


def test_the_minimum_size_is_a_real_document(tmp_path: Path) -> None:
    """The threshold is well below a real resume and well above a stub."""
    assert MIN_RESUME_BYTES >= 512
    path = tmp_path / "small.pdf"
    path.write_bytes(_pdf(size=1))
    with pytest.raises(ProfileNotFoundError):
        validate_resume(path)
