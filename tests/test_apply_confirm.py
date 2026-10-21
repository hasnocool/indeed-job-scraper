"""The confirm gate must stand between a filled form and a submission.

A posting is only submitted when the operator explicitly approves it. This
test drives the real worker with a fake page and a console whose answer is
recorded, so a regression that submits without approval fails here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from indeed_scraper.apply.exceptions import ApplyBlockedError
from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.profile import Profile
from indeed_scraper.apply.worker import _apply_one


class _FakeLocator:
    """Minimal Playwright Locator stand-in."""

    def __init__(self, page: _FakePage, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> _FakeLocator:
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        return self._selector in self._page.visible

    def fill(self, value: str) -> None:
        self._page.filled[self._selector] = value
        self._page.on_fill()

    def set_input_files(self, path: str) -> None:
        self._page.uploaded.append(path)

    def get_attribute(self, name: str) -> str | None:
        return None

    def click(self, timeout: int = 0) -> None:
        self._page.clicks.append(self._selector)

    def evaluate(self, expression: str) -> None:
        self._page.clicks.append(self._selector)

    def count(self) -> int:
        return 0

    def text_content(self) -> str | None:
        return None


class _FakePage:
    """Minimal Playwright Page stand-in for a fillable Indeed form."""

    def __init__(self, url: str, visible: set[str]) -> None:
        self.url = url
        self.visible = visible
        self.filled: dict[str, str] = {}
        self.uploaded: list[str] = []
        self.clicks: list[str] = []
        self.content_html = "<html></html>"
        self.title_text = "Apply"

    def on_fill(self) -> None:
        """Hook: a subclass may turn the page into a challenge here."""

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url

    def wait_for_timeout(self, ms: int) -> None:
        return None

    def title(self) -> str:
        return self.title_text

    def content(self) -> str:
        return self.content_html

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)


class _FakeConsole:
    """Console whose input() returns a scripted answer."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []
        self.messages: list[str] = []

    def print(self, message: Any = "") -> None:
        self.messages.append(str(message))

    def input(self, prompt: str = "") -> str:
        self.prompts.append(prompt)
        return self.answer


class _FakeStore:
    """Cookie store stand-in that reports a signed-in session."""

    class _Session:
        def is_signed_in(self) -> bool:
            return True

    def current(self) -> Any:
        return self._Session()


def _config(tmp_path: Path):
    from indeed_scraper.config import Config

    return Config.load(state_dir=tmp_path)


def _page(tmp_path: Path) -> _FakePage:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    visible = {
        'input[name="applicant.name"]',
        'input[name="applicant.email"]',
        'input[name="applicant.phone"]',
        'input[type="file"]',
        'button:has-text("Apply now")',
        'button:has-text("Submit application")',
    }
    return _FakePage("https://ca.indeed.com/viewjob?jk=jk1", visible)


def _profile(tmp_path: Path) -> Profile:
    return Profile(
        name="Ada Lovelace",
        email="ada@example.com",
        phone="250-555-0142",
        resume_path=str(tmp_path / "resume.pdf"),
    )


def _job():
    from indeed_scraper.scraper import Job

    return Job(
        jk="jk1",
        title="Senior Data Engineer",
        company="Acme",
        location="Vancouver, BC",
        url="https://ca.indeed.com/viewjob?jk=jk1",
    )


def test_a_declined_submission_is_not_submitted(tmp_path: Path) -> None:
    """When the operator does not approve, nothing is submitted."""
    page = _page(tmp_path)
    console = _FakeConsole("no")
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")

    result = _apply_one(
        page,
        _job(),
        "fp-decline",
        _profile(tmp_path),
        ledger,
        _config(tmp_path),
        console,
        confirm=True,
        dry_run=False,
    )

    assert result.status == "failed"
    assert result.detail == "operator_declined"
    assert ledger.status_of("fp-decline") == "failed"
    assert 'button:has-text("Submit application")' not in page.clicks
    assert console.prompts, "the operator was never asked to confirm"


def test_an_approved_submission_is_submitted_once(tmp_path: Path) -> None:
    """An explicit approval submits the application and records it."""
    page = _page(tmp_path)
    console = _FakeConsole("yes")
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")

    result = _apply_one(
        page,
        _job(),
        "fp-approve",
        _profile(tmp_path),
        ledger,
        _config(tmp_path),
        console,
        confirm=True,
        dry_run=False,
    )

    assert result.status == "submitted"
    assert ledger.status_of("fp-approve") == "submitted"
    assert page.clicks.count('button:has-text("Submit application")') == 1


def test_dry_run_never_submits(tmp_path: Path) -> None:
    """A rehearsal fills the form and never touches the submit control."""
    page = _page(tmp_path)
    console = _FakeConsole("yes")
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")

    result = _apply_one(
        page,
        _job(),
        "fp-dry",
        _profile(tmp_path),
        ledger,
        _config(tmp_path),
        console,
        confirm=True,
        dry_run=True,
    )

    assert result.status == "failed"
    assert result.detail == "dry_run"
    assert 'button:has-text("Submit application")' not in page.clicks
    assert ledger.status_of("fp-dry") == "failed"


def test_resume_refuses_a_posting_that_was_already_submitted(tmp_path: Path) -> None:
    """A resume must never re-submit a posting that already reached a terminal state."""
    from indeed_scraper.apply.flow import resume_application
    from indeed_scraper.apply.workspace import drafts_dir

    config = _config(tmp_path)
    ledger = ApplicationLedger(config.state_dir / "applications" / "ledger.jsonl")
    ledger.reserve("fp-done", "jk1", "https://ca.indeed.com/viewjob?jk=jk1")
    ledger.mark("fp-done", "submitted", "")

    draft_root = drafts_dir(config)
    (draft_root / "fp-done").mkdir(parents=True, exist_ok=True)
    (draft_root / "fp-done" / "draft.json").write_text(
        '{"fingerprint": "fp-done", "current_url": "https://ca.indeed.com/viewjob?jk=jk1"}',
        encoding="utf-8",
    )

    console = _FakeConsole("yes")
    result = resume_application(
        config,
        _FakeStore(),
        console,
        "fp-done",
        profile=_profile(tmp_path),
        confirm=True,
    )

    assert result is None
    assert any("already submitted" in message for message in console.messages)


def test_a_challenge_appearing_after_the_fill_stops_the_run(tmp_path: Path) -> None:
    """A wall that appears mid-fill must stop the run before any submit."""

    class _ChallengingPage(_FakePage):
        def on_fill(self) -> None:
            self.title_text = "Just a moment..."

    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    page = _ChallengingPage(
        "https://ca.indeed.com/viewjob?jk=jk1",
        {
            'input[name="applicant.name"]',
            'input[name="applicant.email"]',
            'input[name="applicant.phone"]',
            "input[type=\"file\"]",
            'button:has-text("Apply now")',
            'button:has-text("Submit application")',
        },
    )
    console = _FakeConsole("yes")
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")

    with pytest.raises(ApplyBlockedError):
        _apply_one(
            page,
            _job(),
            "fp-wall",
            _profile(tmp_path),
            ledger,
            _config(tmp_path),
            console,
            confirm=True,
            dry_run=False,
        )

    assert 'button:has-text("Submit application")' not in page.clicks
    assert ledger.status_of("fp-wall") == "blocked"
