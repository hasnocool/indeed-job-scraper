"""Wave 2 — a challenge must exit 3, not 2.

**W1 MAJOR.** ``exit_code_for`` decides "a challenge stopped this run" by
looking for the word "challenge" in the result detail. The flow built that
detail as ``str(error)``, and ``str()`` of an exception whose ``__init__``
never called ``super().__init__(...)`` is the REPR OF ITS ARGS TUPLE::

    str(ApplyBlockedError("Indeed security check", "https://x"))
    == "('Indeed security check', 'https://x')"

which does not contain the word "challenge". So a real "Indeed security
check" wall exited 2 - "attempt failed" - instead of 3 - "wall, back off".

Nothing was submitted and the run stopped safely, so this is not a safety
failure. But the exit code is the machine-readable signal, and it lies
about WHY the run stopped. An automated caller acts on it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from indeed_scraper.apply.exceptions import ApplyBlockedError
from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.profile import Profile
from indeed_scraper.apply.types import ApplyResult
from indeed_scraper.apply.worker import _apply_one
from indeed_scraper.commands.apply import exit_code_for


def _result(status: str, detail: str = "") -> ApplyResult:
    return ApplyResult(
        jk="jk1",
        title="Engineer",
        company="Acme",
        location="Vancouver, BC",
        url="https://ca.indeed.com/viewjob?jk=jk1",
        status=status,
        fingerprint="fp-1",
        app_id="fp-1",
        portal="indeed",
        detail=detail,
    )


def test_a_challenge_marker_survives_into_the_result_detail() -> None:
    """The detail must carry the marker ``exit_code_for`` looks for.

    The ledger already uses ``challenge:<kind>`` as its marker, so the
    result uses the SAME convention: one spelling, used by both.
    """
    error = ApplyBlockedError("Indeed security check", "https://x")
    detail = f"challenge:{error}"

    assert "challenge" in detail, f"the marker is missing: {detail!r}"


def test_the_exception_itself_says_what_kind_of_block_it_was() -> None:
    """``str(error)`` must be the challenge kind, not the args tuple.

    The old ``str()`` was ``"('Indeed security check', 'https://x')"`` -
    the repr of the args tuple - which is why the marker never appeared
    anywhere the detail was built from it.
    """
    error = ApplyBlockedError("Indeed security check", "https://x")

    text = str(error)
    assert "Indeed security check" in text, f"the challenge kind is missing: {text!r}"
    assert not text.startswith("("), f"the args tuple leaked into the message: {text!r}"


def test_a_challenge_result_exits_three() -> None:
    """A challenge must be exit code 3, not 2."""
    results = [_result("blocked", "challenge:Indeed security check")]
    assert exit_code_for(results) == 3


def test_a_non_challenge_block_still_exits_two() -> None:
    """A block that is NOT a challenge is not "back off for a wall"."""
    results = [_result("blocked", "missing:email")]
    assert exit_code_for(results) == 2


def test_the_other_exit_codes_do_not_change() -> None:
    """The existing behaviour must not move."""
    assert exit_code_for([]) == 0
    assert exit_code_for([_result("submitted")]) == 0
    assert exit_code_for([_result("unconfirmed")]) == 2
    assert exit_code_for([_result("failed")]) == 2
    assert exit_code_for([_result("failed", "dry_run")], dry_run=True) == 0


# ---------------------------------------------------------------------------
# The whole path: a challenge raised through the flow
# ---------------------------------------------------------------------------

class _ChallengingLocator:
    def __init__(self, page: _ChallengingPage) -> None:
        self._page = page

    @property
    def first(self) -> _ChallengingLocator:
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        return True

    def click(self, timeout: int = 0) -> None:
        self._page.clicked = True

    def evaluate(self, expression: str) -> None:
        self._page.clicked = True


class _ChallengingPage:
    """A page whose title is a challenge wall."""

    def __init__(self) -> None:
        self.url = "https://ca.indeed.com/viewjob?jk=jk1"
        self.title_text = "Indeed security check"
        self.clicked = False

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url

    def wait_for_timeout(self, ms: int) -> None:
        return None

    def title(self) -> str:
        return self.title_text

    def content(self) -> str:
        return "<html><body>security check</body></html>"

    def locator(self, selector: str) -> _ChallengingLocator:
        return _ChallengingLocator(self)


class _Console:
    def print(self, message: Any = "") -> None:
        return None

    def input(self, prompt: str = "") -> str:
        return "yes"


def test_a_challenge_raised_through_the_flow_carries_the_marker(
    tmp_path: Path,
) -> None:
    """The whole path: the flow must produce a detail the exit code reads.

    This is the end-to-end version of the defect. Before the fix the
    detail was the exception's args-tuple repr, the marker was absent,
    and the run exited 2 - "an attempt failed" - for what was actually a
    wall the operator must back off from.
    """
    from indeed_scraper.config import Config

    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    profile = Profile(
        name="Ada",
        email="ada@example.com",
        phone="555-0100",
        resume_path=str(resume),
    )
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    config = Config.load(state_dir=tmp_path)

    from indeed_scraper.scraper import Job

    job = Job(
        jk="jk1",
        title="Engineer",
        company="Acme",
        location="Vancouver, BC",
        url="https://ca.indeed.com/viewjob?jk=jk1",
    )

    with pytest.raises(ApplyBlockedError):
        _apply_one(
            _ChallengingPage(),
            job,
            "fp-1",
            profile,
            ledger,
            config,
            _Console(),
            confirm=False,
            dry_run=False,
        )

    # The ledger's own marker is the convention the result uses.
    assert ledger.status_of("fp-1") == "blocked"
    assert "challenge" in (ledger.entries[-1].get("detail") or "").lower()
