"""Wave 2 — ``check-responses`` must actually check the responses.

**U3 MAJOR.** ``collect_responses`` takes an optional ``fetch_status``
callable and uses it to read the employer's live status. The ``check-
responses`` command never passed one, so EVERY record came out with
``status="unknown"`` - the command reported the status of nothing.

The vocabulary was fixed in wave 1, but the WIRING was not: the command
reached the monitor with no way to ask Indeed anything.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from indeed_scraper.apply.ledger import ApplicationLedger

#: A realistic Indeed tracker card, as the page renders it.
REAL_CARD_LINES = [
    "Interviewing",
    "Veteran Community Relations & Business Development Specialist - Libertyville, IL 60048",
    "Assure Home Assist Inc",
    "Libertyville, IL 60048",
    "Applied on Indeed on Tuesday",
]


class _TrackerPage:
    """A page double that returns one realistic tracker card."""

    def __init__(self, cards: list[list[str]], jk: str = "jk-1") -> None:
        self._cards = cards
        self._jk = jk
        self.goto_calls: list[str] = []

    def goto(self, url: str, **kwargs: Any) -> None:
        self.goto_calls.append(url)

    def wait_for_timeout(self, ms: int) -> None:
        return None

    def evaluate(self, script: str) -> list[dict]:
        return [{"lines": list(lines), "jk": self._jk} for lines in self._cards]


def test_a_fetcher_reads_the_tracker_and_reports_a_real_status() -> None:
    """The fetcher the command uses must produce a REAL status.

    This is the piece the command was missing: a callable that opens the
    tracker, reads the rows, and returns the status text for a job.
    """
    from indeed_scraper.apply.tracker import status_fetcher_for

    page = _TrackerPage([REAL_CARD_LINES])
    fetch = status_fetcher_for(page)

    text = fetch("jk-1")

    assert text, "the fetcher returned nothing"
    assert "Interviewing" in text, f"the tracker status was not read: {text!r}"


def test_the_fetcher_never_raises_for_an_unknown_job() -> None:
    """A job that is not on the tracker must not break the command.

    The command checks EVERY application; one of them not being on the
    tracker is normal, not an error.
    """
    from indeed_scraper.apply.tracker import status_fetcher_for

    page = _TrackerPage([REAL_CARD_LINES])
    fetch = status_fetcher_for(page)

    assert fetch("jk-not-there") == ""


def test_the_check_responses_command_produces_a_real_status(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The end-to-end check: the command must not report "unknown".

    Before the fix the command called ``collect_responses`` without a
    ``fetch_status``, so every record was ``status="unknown"`` and the
    operator's status report was empty of information.
    """
    from typer.testing import CliRunner

    from indeed_scraper import cli

    state = tmp_path / "state"
    master = state / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "jobs_master.json").write_text(
        json.dumps({"meta": {"query": "", "locations": ["X"], "total_jobs": 0}, "jobs": []}),
        encoding="utf-8",
    )
    from indeed_scraper.config import Config

    config = Config.load(state_dir=state)

    ledger = ApplicationLedger(state / "applications" / "ledger.jsonl")
    ledger.reserve("fp-1", "jk-1", "https://ca.indeed.com/viewjob?jk=jk1")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "submitted", "")

    page = _TrackerPage([REAL_CARD_LINES])

    from indeed_scraper.commands import resume_cmds

    monkeypatch.setattr(cli, "_config", lambda **kwargs: config)
    monkeypatch.setattr(resume_cmds, "_open_tracker_page", lambda *a, **k: page)
    # The store is imported inside the command, so the patch goes on the
    # class itself - that is the object the command looks up.
    from indeed_scraper.cookies import CookieStore

    monkeypatch.setattr(CookieStore, "current", lambda self: _signed_in_session())

    runner = CliRunner()
    outcome = runner.invoke(cli.app, ["check-responses"])

    assert outcome.exit_code == 0, outcome.output
    assert "unknown" not in outcome.output.lower(), (
        f"the command reported an unknown status for every record:\n{outcome.output}"
    )
    assert "interview" in outcome.output.lower(), (
        f"the command did not report the real status:\n{outcome.output}"
    )


def test_the_monitor_uses_the_fetcher_when_it_is_given_one(tmp_path: Path) -> None:
    """The monitor must prefer the live status over its own default."""
    from indeed_scraper.response_monitor.indeed import collect_responses

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp-1", "jk-1", "https://ca.indeed.com/viewjob?jk=jk1")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "submitted", "")

    records = collect_responses(
        ledger.path,
        tmp_path / "responses",
        fetch_status=lambda jk: "Interviewing",
    )

    assert len(records) == 1
    assert records[0]["status"] == "interview"


def _signed_in_session():
    """A session that reports itself as signed in."""
    from indeed_scraper.cookies import Cookie, CookieSession

    return CookieSession(
        id="sess-1",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        source="login",
        cookies=(
            Cookie(
                name="__Secure-PassportAuthProxy-BearerToken",
                value="x",
                domain=".indeed.com",
                path="/",
            ),
        ),
    )
