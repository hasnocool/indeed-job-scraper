"""Wave 2 — a missing resume upload must BLOCK the submission.

**U1 MAJOR.** Two defects in one:

1. A ``~/…`` resume path reached ``set_input_files`` unexpanded. The
   browser was handed the literal string ``~/Documents/resume.pdf``, the
   upload silently failed, and the run went on to submit.
2. A failed resume upload was a WARNING, not a BLOCK. The run submitted an
   application with no resume, and the employer received it.

The resume is the one file that is UPLOADED to an employer. A missing
resume upload is a hard block, not a warning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indeed_scraper.apply.exceptions import FieldMissingError
from indeed_scraper.apply.indeed_form import fill_indeed_form
from indeed_scraper.apply.profile import Profile


class _Locator:
    """Locator stand-in that records what it was handed."""

    def __init__(self, page: _Page, selector: str, *, upload_raises: bool = False) -> None:
        self._page = page
        self._selector = selector
        self._upload_raises = upload_raises

    @property
    def first(self) -> _Locator:
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        return self._selector in self._page.visible

    def fill(self, value: str) -> None:
        self._page.filled.append((self._selector, value))

    def set_input_files(self, path: str) -> None:
        self._page.uploads.append(path)
        if self._upload_raises:
            raise RuntimeError("the file input refused the file")


class _Page:
    """A page with a name field and (optionally) a file input."""

    def __init__(self, *, with_file_input: bool = True, upload_raises: bool = False) -> None:
        self.url = "https://ca.indeed.com/apply/in/jk1"
        self.visible = {'input[name="applicant.name"]'}
        self.filled: list[tuple[str, str]] = []
        self.uploads: list[str] = []
        self._upload_raises = upload_raises
        if with_file_input:
            self.visible.add('input[type="file"]')

    def locator(self, selector: str) -> _Locator:
        return _Locator(self, selector, upload_raises=self._upload_raises)


def _profile(tmp_path: Path, resume_path: str | None = None) -> Profile:
    target = tmp_path / "resume.pdf"
    target.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    return Profile(
        name="Ada",
        email="ada@example.com",
        phone="555-0100",
        resume_path=resume_path if resume_path is not None else str(target),
    )


def test_a_tilde_path_reaches_the_file_input_expanded(tmp_path: Path) -> None:
    """The file input must be handed a REAL path, not the literal ``~/…``.

    The browser does not expand a tilde: it received
    ``~/Documents/resume.pdf``, which does not exist, so the upload failed
    silently and the application went out with no resume.
    """
    home = tmp_path / "home"
    documents = home / "Documents"
    documents.mkdir(parents=True)
    real_resume = documents / "resume.pdf"
    real_resume.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)

    page = _Page()
    profile = _profile(tmp_path, resume_path="~/Documents/resume.pdf")

    # Point HOME at our temporary home so the tilde resolves to it.
    import os

    previous = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        fill_indeed_form(page, profile)
    finally:
        if previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous

    assert page.uploads, "the resume was never handed to the file input"
    handed = page.uploads[0]
    assert not handed.startswith("~"), f"the tilde was never expanded: {handed!r}"
    assert Path(handed).is_file(), f"the file input was handed a path that does not exist: {handed!r}"


def test_a_failed_resume_upload_blocks_the_fill(tmp_path: Path) -> None:
    """A file input that REFUSES the file is a hard block.

    The employer must not receive an application with no resume. The old
    code swallowed the failure, recorded ``resume_status="no_input"`` and
    let the run submit.
    """
    page = _Page(upload_raises=True)
    profile = _profile(tmp_path)

    with pytest.raises(FieldMissingError) as excinfo:
        fill_indeed_form(page, profile)

    assert "resume" in excinfo.value.question.lower()


def test_a_failed_resume_upload_is_not_reported_as_no_input(tmp_path: Path) -> None:
    """A REFUSED upload is not the same as "the form has no file input".

    The two cases need different words: "no_input" says the form does not
    take a resume at all, which is a legitimate outcome. A refused upload
    says we HAD a resume and it did not go through, which is a failure.
    """
    page = _Page(upload_raises=True)
    profile = _profile(tmp_path)

    with pytest.raises(FieldMissingError):
        fill_indeed_form(page, profile)

    # The page DID have a file input: the upload was attempted.
    assert page.uploads, "the upload was never even attempted"


def test_a_form_with_no_file_input_is_still_filled(tmp_path: Path) -> None:
    """A form that takes no resume is not a failure.

    The resume is not on every form. This case keeps its honest label
    (``resume_status="no_input"``) so the operator can see it, and it does
    not block - there was nothing to fail.
    """
    page = _Page(with_file_input=False)
    profile = _profile(tmp_path)

    draft = fill_indeed_form(page, profile)

    assert draft.get("resume_status") == "no_input"
    assert "resume" not in draft
