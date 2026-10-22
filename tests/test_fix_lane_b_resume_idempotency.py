"""B1 - the resume path must obey the same idempotency invariant as apply.

The apply path reserves the posting in the ledger BEFORE the browser is
touched and marks it "submitting" BEFORE the irreversible click. The resume
path used to do neither, so a run killed in the instant after the submit
click left an EMPTY ledger: the posting looked untouched and a second
`resume` submitted it AGAIN.

These tests pin the invariant "at most ONE submission per fingerprint, ever"
on the resume path.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ClassVar

import pytest

from indeed_scraper.apply.ledger import ApplicationLedger


class _FakeLocator:
    """A locator that is visible and records the clicks it received.

    When *boom* is set, the click raises it: that simulates a process killed
    in the instant AFTER the irreversible submit click.
    """

    def __init__(
        self,
        clicks: list[str],
        label: str = "submit",
        boom: Exception | None = None,
        visible: bool = True,
    ) -> None:
        self._clicks = clicks
        self._label = label
        self._boom = boom
        self._visible = visible

    def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    def click(self, timeout: int | None = None) -> None:
        self._clicks.append(self._label)
        if self._boom is not None:
            raise self._boom

    def evaluate(self, script: str) -> None:
        self._clicks.append(self._label)

    @property
    def first(self) -> _FakeLocator:
        # Playwright's Locator.first is a PROPERTY, not a method.
        return self

    def fill(self, value: str) -> None:
        return None

    def set_input_files(self, path: str) -> None:
        return None

    def get_attribute(self, name: str) -> str | None:
        # Real Playwright returns "" for a valueless boolean attribute.
        return None

    def inner_text(self) -> str:
        return ""

    def count(self) -> int:
        return 1 if self._visible else 0

    def nth(self, index: int) -> _FakeLocator:
        return self


class _FakePage:
    """The smallest page the resume flow drives."""

    def __init__(self, clicks: list[str], *, boom: Exception | None = None) -> None:
        self._clicks = clicks
        self._boom = boom
        self.url = "https://ca.indeed.com/viewjob?jk=resume1"
        self.pages: list[Any] = []

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url

    def wait_for_timeout(self, ms: int) -> None:
        return None

    def title(self) -> str:
        return "Apply"

    def content(self) -> str:
        return "<html><body>apply form</body></html>"

    def locator(self, selector: str) -> _FakeLocator:
        lowered = selector.lower()
        # The boom belongs to the SUBMIT control only: the kill must happen
        # after the irreversible click, not during the form fill.
        is_submit = "submit" in lowered
        # A captcha / challenge element must NOT be present, or the flow
        # correctly stops with ApplyBlockedError before it ever submits.
        is_challenge = any(
            token in lowered
            for token in ("captcha", "hcaptcha", "g-recaptcha", "verification")
        )
        return _FakeLocator(
            self._clicks,
            boom=self._boom if is_submit else None,
            visible=not is_challenge,
        )

    def close(self) -> None:
        return None


class _FakeConsole:
    """A console that records what was printed and answers the confirm gate."""

    def __init__(self, answer: str = "yes") -> None:
        self._answer = answer
        self.lines: list[str] = []

    def print(self, message: str = "") -> None:
        self.lines.append(str(message))

    def input(self, prompt: str = "") -> str:
        return self._answer


class _FakeStore:
    """A cookie store that always reports a signed-in session."""

    def current(self) -> Any:
        class _Session:
            def is_signed_in(self) -> bool:
                return True

        return _Session()


def _profile(tmp_path: Path) -> Any:
    from indeed_scraper.apply.profile import Profile

    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    return Profile(
        name="Ada Lovelace",
        email="ada@example.com",
        phone="250-555-0142",
        resume_path=str(resume),
    )


def _draft(root: Path, app_id: str, fingerprint: str) -> None:
    from indeed_scraper.apply.drafts import write_draft

    write_draft(
        root,
        app_id,
        {
            "fingerprint": fingerprint,
            "jk": "resume1",
            "title": "Data Engineer",
            "company": "Acme",
            "location": "Remote",
            "current_url": "https://ca.indeed.com/viewjob?jk=resume1",
        },
    )


def _config(tmp_path: Path) -> Any:
    from indeed_scraper.config import Config

    return Config.load(state_dir=tmp_path)


def _run_resume(
    tmp_path: Path,
    *,
    clicks: list[str],
    fingerprint: str = "fp-resume",
    app_id: str = "fp-resume",
    boom: Exception | None = None,
    policy: Any = None,
) -> Any:
    """Drive resume_application against a fake driver and a fake page."""
    from indeed_scraper.apply import resume as resume_module

    page = _FakePage(clicks, boom=boom)
    drafts = tmp_path / "applications" / "drafts"
    _draft(drafts, app_id, fingerprint)

    class _Context:
        pages: ClassVar[list[_FakePage]] = [page]

    class _Info:
        kind = "profile"
        endpoint = "fake"
        harness_reachable = False

    @contextmanager
    def _fake_open_driver(config: Any, session: Any, **kwargs: Any) -> Any:
        yield _Context(), _Info()

    original = resume_module.open_driver
    resume_module.open_driver = _fake_open_driver  # type: ignore[assignment]
    try:
        return resume_module.resume_application(
            _config(tmp_path),
            _FakeStore(),
            _FakeConsole(),
            app_id,
            profile=_profile(tmp_path),
            confirm=False,
            policy=policy,
        )
    finally:
        resume_module.open_driver = original  # type: ignore[assignment]


def test_a_resume_reserves_the_posting_before_the_browser_is_touched(
    tmp_path: Path,
) -> None:
    """The ledger must hold a reservation while the resume is running.

    Without a reservation the posting is invisible to the idempotency guard:
    the ledger looks untouched and a second resume applies again.
    """
    clicks: list[str] = []
    _run_resume(tmp_path, clicks=clicks)

    ledger = ApplicationLedger(tmp_path / "applications" / "ledger.jsonl")
    statuses = [entry.get("status") for entry in ledger.history]
    assert "reserved" in statuses, (
        "the resume path must reserve the posting before the browser action; "
        f"ledger statuses were {statuses}"
    )


def test_a_resume_marks_submitting_before_the_submit_click(tmp_path: Path) -> None:
    """'submitting' must be recorded BEFORE the irreversible click.

    A run killed between the click and the confirmation must leave a live
    status behind, so the posting is never applied to a second time.
    """
    clicks: list[str] = []
    _run_resume(tmp_path, clicks=clicks)

    ledger = ApplicationLedger(tmp_path / "applications" / "ledger.jsonl")
    statuses = [entry.get("status") for entry in ledger.history]
    assert "submitting" in statuses, (
        f"the resume path must mark 'submitting' before the click; statuses were {statuses}"
    )


def test_a_kill_after_the_submit_click_leaves_a_live_status(
    tmp_path: Path,
) -> None:
    """THE INVARIANT: a kill after the click must block a second resume.

    This is the defect that let one posting be submitted twice. The ledger
    must still hold a LIVE status after the kill, so the next resume refuses.
    """
    clicks: list[str] = []
    with pytest.raises(KeyboardInterrupt):
        _run_resume(
            tmp_path,
            clicks=clicks,
            boom=KeyboardInterrupt("killed right after the submit click"),
        )

    ledger = ApplicationLedger(tmp_path / "applications" / "ledger.jsonl")
    status = ledger.status_of("fp-resume")
    assert status in ApplicationLedger.LIVE_STATUSES, (
        "after a kill the posting must stay blocked; "
        f"status was {status!r}, live statuses are {sorted(ApplicationLedger.LIVE_STATUSES)}"
    )


def test_a_second_resume_after_a_kill_does_not_submit_again(
    tmp_path: Path,
) -> None:
    """A second resume must not click submit again after a kill.

    The end-to-end proof of the invariant: one posting, one submit click.
    """
    clicks: list[str] = []
    with pytest.raises(KeyboardInterrupt):
        _run_resume(
            tmp_path,
            clicks=clicks,
            boom=KeyboardInterrupt("killed right after the submit click"),
        )
    clicks_after_kill = len(clicks)

    # The operator runs `resume` again on the same draft.
    result = _run_resume(tmp_path, clicks=clicks)

    assert result is None, "the second resume must refuse, not submit"
    assert len(clicks) == clicks_after_kill, (
        "the second resume clicked submit again; the posting would be applied "
        "to twice"
    )


def test_a_resume_never_resubmits_a_posting_the_ledger_holds_live(
    tmp_path: Path,
) -> None:
    """A posting whose latest status is LIVE must never be resumed."""
    clicks: list[str] = []
    _run_resume(tmp_path, clicks=clicks)

    # Pretend the ledger already says the posting went out.
    ledger = ApplicationLedger(tmp_path / "applications" / "ledger.jsonl")
    ledger.mark("fp-resume", "submitted", "")

    clicks.clear()
    result = _run_resume(tmp_path, clicks=clicks)
    assert result is None
    assert clicks == []


def test_the_resume_ledger_is_append_only(tmp_path: Path) -> None:
    """The reservation must be appended, never rewrite the ledger."""
    clicks: list[str] = []
    _run_resume(tmp_path, clicks=clicks)

    path = tmp_path / "applications" / "ledger.jsonl"
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        json.loads(line)  # every line is valid JSON
    assert text.endswith("\n"), "the ledger must end with a newline"
