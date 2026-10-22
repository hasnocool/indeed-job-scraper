"""C4: the ``apply`` command must tell success from failure in its exit code.

The command printed its table and returned normally whatever happened, so a
CI job or a wrapper script could not tell "submitted three applications"
from "every posting failed". The exit code is the machine-readable signal,
so it has to reflect the outcome.

The mapping under test:

======  ==========================================================
``0``   something was submitted, or a dry-run did what it was asked
``2``   nothing was submitted and at least one attempt failed
``3``   the run was blocked by a challenge (CAPTCHA / auth wall)
======  ==========================================================

A clean dry-run exits 0 (it did exactly what it was asked to do), and
"nothing to apply to" is not a failure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from indeed_scraper.apply.types import ApplyResult


def _result(status: str, detail: str = "", title: str = "Senior Data Engineer") -> ApplyResult:
    return ApplyResult(
        jk="jk1",
        title=title,
        company="Acme",
        location="Vancouver, BC",
        url="https://ca.indeed.com/viewjob?jk=jk1",
        fingerprint="fp1",
        app_id="app-1",
        portal="indeed",
        status=status,
        detail=detail,
    )


@pytest.mark.parametrize(
    ("results", "dry_run", "expected"),
    [
        # Something went out: success.
        ([_result("submitted")], False, 0),
        ([_result("submitted"), _result("failed", "boom")], False, 0),
        # Nothing went out and something failed: failure.
        ([_result("failed", "submit_not_confirmed")], False, 2),
        ([_result("failed", "boom"), _result("failed", "bang")], False, 2),
        # A challenge stops the run: its own code.
        ([_result("blocked", "challenge:captcha")], False, 3),
        # A dry-run did exactly what it was asked to do.
        ([_result("failed", "dry_run")], True, 0),
        # Nothing to do is not a failure.
        ([], False, 0),
    ],
)
def test_the_exit_code_reflects_the_outcome(
    results: list[ApplyResult], dry_run: bool, expected: int
) -> None:
    from indeed_scraper.commands.apply import exit_code_for

    assert exit_code_for(results, dry_run=dry_run) == expected


def test_a_dry_run_never_submits_at_any_policy_level(tmp_path: Path) -> None:
    """``--dry-run`` is a rehearsal: it must never reach the submit click.

    Opening the application form (the "Apply now" control) is part of the
    rehearsal - the form has to be reached to be filled. What must never
    happen is the SUBMIT control being clicked, so that is what is recorded
    here: the fake locator records the selector it was asked to click, and
    only a submit control counts as a submission.
    """
    from indeed_scraper.apply.worker import _fill_and_submit

    #: Selectors that SUBMIT an application. Clicking any of these sends a
    #: real application to a real employer.
    submit_selectors = (
        'button:has-text("Submit application")',
        'button:has-text("Submit")',
        'input[type="submit"]',
        '[data-testid="submit-application"]',
    )
    submitted: list[str] = []

    class _Locator:
        def __init__(self, page: Any, selector: str) -> None:
            self._page = page
            self._selector = selector

        @property
        def first(self) -> _Locator:
            return self

        def is_visible(self, timeout: int = 0) -> bool:
            return True

        def fill(self, value: str) -> None:
            return None

        def set_input_files(self, path: str) -> None:
            return None

        def get_attribute(self, name: str) -> str | None:
            return None

        def click(self, timeout: int = 0) -> None:
            if self._selector in submit_selectors:
                submitted.append(self._selector)

        def evaluate(self, expression: str) -> None:
            return None

        def count(self) -> int:
            return 0

        def text_content(self) -> str | None:
            return None

    class _Page:
        url = "https://ca.indeed.com/viewjob?jk=jk1"

        def locator(self, selector: str) -> _Locator:
            return _Locator(self, selector)

        def wait_for_timeout(self, ms: int) -> None:
            return None

        def title(self) -> str:
            return "Apply"

        def content(self) -> str:
            return "<html></html>"

    from indeed_scraper.apply.ledger import ApplicationLedger
    from indeed_scraper.apply.profile import Profile
    from indeed_scraper.config import Config

    config = Config.load(state_dir=tmp_path)
    config.ensure_dirs()
    ledger = ApplicationLedger(config.state_dir / "applications" / "ledger.jsonl")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    profile = Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path=str(resume),
    )

    for level in ("manual", "auto", "full"):
        result = _fill_and_submit(
            _Page(),  # type: ignore[arg-type]
            _FakeJob(),
            "fp-dry",
            profile,
            ledger,
            config,
            _SilentConsole(),  # type: ignore[arg-type]
            confirm=True,
            dry_run=True,
        )
        assert result.status == "failed", level
        assert result.detail == "dry_run", level

    assert submitted == [], "a dry-run clicked a submit control"


class _FakeJob:
    jk = "jk1"
    title = "Senior Data Engineer"
    company = "Acme"
    location = "Vancouver, BC"
    url = "https://ca.indeed.com/viewjob?jk=jk1"


class _SilentConsole:
    def print(self, message: Any = "") -> None:
        return None

    def input(self, prompt: str = "") -> str:
        raise AssertionError("a dry-run must never prompt")


def test_the_apply_command_exits_non_zero_when_everything_failed(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The end-to-end signal: a run where every posting failed is a failure."""
    from typer.testing import CliRunner

    from indeed_scraper import cli

    monkeypatch.setattr(cli, "_config", lambda **kwargs: _config(tmp_path))
    monkeypatch.setattr(
        "indeed_scraper.apply.flow.apply_to_jobs",
        lambda *a, **k: [_result("failed", "submit_not_confirmed")],
    )
    monkeypatch.setattr(
        "indeed_scraper.apply.profile.load_profile",
        lambda *a, **k: _profile(tmp_path),
    )

    runner = CliRunner()
    outcome = runner.invoke(cli.app, ["apply", "--limit", "1"])
    assert outcome.exit_code != 0, "a run where every posting failed exited 0"
    assert outcome.exit_code == 2


def test_the_apply_command_exits_zero_for_a_successful_dry_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A rehearsal that did what it was asked to do is a success."""
    from typer.testing import CliRunner

    from indeed_scraper import cli

    monkeypatch.setattr(cli, "_config", lambda **kwargs: _config(tmp_path))
    monkeypatch.setattr(
        "indeed_scraper.apply.flow.apply_to_jobs",
        lambda *a, **k: [_result("failed", "dry_run")],
    )
    monkeypatch.setattr(
        "indeed_scraper.apply.profile.load_profile",
        lambda *a, **k: _profile(tmp_path),
    )

    runner = CliRunner()
    outcome = runner.invoke(cli.app, ["apply", "--dry-run", "--limit", "1"])
    assert outcome.exit_code == 0, outcome.output


def _config(tmp_path: Path):
    from indeed_scraper.config import Config

    master = tmp_path / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "jobs_master.json").write_text(
        json.dumps({"meta": {"query": "", "locations": ["X"], "total_jobs": 0}, "jobs": []}),
        encoding="utf-8",
    )
    return Config.load(state_dir=tmp_path)


def _profile(tmp_path: Path):
    from indeed_scraper.apply.profile import Profile

    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    return Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path=str(resume),
    )
