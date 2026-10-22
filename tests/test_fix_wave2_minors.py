"""Wave 2 — the minor defects.

**U6 MINOR.** The skip path said "already applied" and reported
``failed``, which inflates the exit code: a run that skipped a posting it
had already applied to is not a FAILED run.

**U7 MINOR.** A relative ``--profile`` was ignored and the default profile
loaded. The operator asked for a specific file and got a different one.

**N3 MINOR.** The resume path never called ``detect_portal``, so it would
resume into a non-Indeed destination the same way the apply path refuses.

**T1 MINOR.** ``messages --autonomy`` still said "Overrides the policy
file", but the flag is CLAMPED to the policy file's level.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from indeed_scraper.apply.profile import load_profile
from indeed_scraper.apply.types import ApplyResult
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


# ---------------------------------------------------------------------------
# U6 — the skip path
# ---------------------------------------------------------------------------

def test_a_skipped_posting_does_not_inflate_the_exit_code() -> None:
    """A skip is not a failure.

    The run did what it was asked: it left an already-applied posting
    alone. Reporting that as "failed" made the exit code say "attempt
    failed" for a run that did exactly the right thing.
    """
    results = [_result("skipped", "duplicate")]
    assert exit_code_for(results) == 0, (
        "a run that only skipped an already-applied posting is not a failure"
    )


def test_a_skip_alongside_a_real_failure_is_still_a_failure() -> None:
    """The exit code must not be softened by a skip."""
    results = [_result("skipped", "duplicate"), _result("failed", "submit_not_found")]
    assert exit_code_for(results) == 2


def test_the_skip_message_says_already_applied_or_reserved() -> None:
    """The wording must match what actually happened.

    "already applied" is wrong for a posting that is merely RESERVED:
    nothing was applied to it, it is held.
    """
    from indeed_scraper.apply.flow import _skip_message

    message = _skip_message()
    assert "already applied or reserved" in message, f"the wording is wrong: {message!r}"


# ---------------------------------------------------------------------------
# U7 — a relative --profile
# ---------------------------------------------------------------------------

def test_a_relative_profile_is_resolved_against_the_current_directory(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A relative ``--profile`` must load THAT file.

    The old code treated a relative path as "no path given" and loaded the
    default profile instead. The operator asked for a specific file and
    silently got a different one.
    """
    profile_path = tmp_path / "my-profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "Ada",
                "email": "ada@example.com",
                "phone": "555-0100",
                "resume_path": str(tmp_path / "resume.pdf"),
            }
        ),
        encoding="utf-8",
    )
    profile_path.chmod(0o600)

    monkeypatch.chdir(tmp_path)

    profile = load_profile(Path("my-profile.json"))

    assert profile.name == "Ada", (
        f"the relative profile was ignored and another one loaded: {profile!r}"
    )


def test_an_absolute_profile_still_works(tmp_path: Path) -> None:
    """An absolute path is unaffected."""
    profile_path = tmp_path / "abs-profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "Ada",
                "email": "ada@example.com",
                "phone": "555-0100",
                "resume_path": str(tmp_path / "resume.pdf"),
            }
        ),
        encoding="utf-8",
    )
    profile_path.chmod(0o600)

    profile = load_profile(profile_path)

    assert profile.name == "Ada"


def test_a_missing_relative_profile_is_an_error(tmp_path: Path, monkeypatch: Any) -> None:
    """A relative profile that does not exist must be reported, not ignored.

    Falling back to the default profile would load a DIFFERENT operator's
    details - or, worse, the wrong resume.
    """
    from indeed_scraper.apply.exceptions import ProfileNotFoundError

    monkeypatch.chdir(tmp_path)

    with pytest.raises(ProfileNotFoundError):
        load_profile(Path("does-not-exist.json"))


# ---------------------------------------------------------------------------
# N3 — the resume path checks the portal
# ---------------------------------------------------------------------------

class _ExternalPage:
    """A page on a non-Indeed domain."""

    url = "https://greenhouse.io/acme/jobs/12345"

    def __init__(self) -> None:
        self.goto_calls: list[str] = []

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url
        self.goto_calls.append(url)

    def wait_for_timeout(self, ms: int) -> None:
        return None

    def title(self) -> str:
        return "Apply"

    def content(self) -> str:
        return "<html></html>"


def test_the_resume_path_refuses_a_non_indeed_destination(tmp_path: Path) -> None:
    """The resume path must apply the same portal guard as the apply path.

    The apply path calls ``detect_portal`` and refuses an external ATS.
    The resume path did not, so it would happily fill and submit on a
    greenhouse page - a site this tool has never checked the selectors
    against.

    An external destination is a PER-POSTING block, exactly as it is on
    the apply path: the posting is marked blocked and the run carries on.
    Only a challenge stops the whole run.
    """
    from indeed_scraper.apply.resume import _portal_reason

    page = _ExternalPage()

    reason = _portal_reason(page)

    assert reason, "an external destination must be refused"
    assert "external" in reason.lower(), f"the wrong reason was given: {reason!r}"


def test_an_indeed_destination_passes_the_guard() -> None:
    """An Indeed page must pass the guard."""

    class _IndeedPage(_ExternalPage):
        url = "https://ca.indeed.com/apply/in/jk1"

    from indeed_scraper.apply.resume import _portal_reason

    assert _portal_reason(_IndeedPage()) == ""


# ---------------------------------------------------------------------------
# T1 — the help text
# ---------------------------------------------------------------------------

def test_the_autonomy_help_does_not_claim_it_overrides_the_policy() -> None:
    """The flag is CLAMPED to the policy file, and the help must say so.

    "Overrides the policy file" told the operator the flag could RAISE
    their level. It cannot: the policy file is the ceiling.
    """
    import inspect

    import indeed_scraper.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "Overrides the policy file" not in source, (
        "the help text still claims the flag overrides the policy file"
    )


def test_the_apply_command_help_does_not_claim_it_overrides_the_policy() -> None:
    """The apply command's help must match its real behaviour too."""
    import inspect

    from indeed_scraper.commands.apply_cmds import register

    source = inspect.getsource(register)
    assert "Overrides the policy file" not in source
