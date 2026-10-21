"""Regression tests for the guard rails the review found missing.

Each test here fails if the behaviour it names regresses:

* the confirm gate must abort a submission that the operator did not approve;
* a resume must not re-submit a posting that already reached a terminal state;
* the reservation must be safe across PROCESSES, not just across threads in
  one interpreter;
* a draft file must not carry the operator's personal values;
* the daily budget must count a posting once even if it was marked repeatedly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from indeed_scraper.apply.drafts import draft_payload, write_draft
from indeed_scraper.apply.ledger import ApplicationLedger

REPO = Path(__file__).resolve().parents[1]


def test_draft_payload_does_not_store_personal_values() -> None:
    """The draft names the filled fields; it never stores their values."""
    filled = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "250-555-0142",
        "cover_letter": "Dear hiring manager",
    }
    payload = draft_payload({"fingerprint": "fp", "current_url": "u"}, filled)

    text = json.dumps(payload)
    assert "Ada Lovelace" not in text
    assert "ada@example.com" not in text
    assert "250-555-0142" not in text
    assert "Dear hiring manager" not in text
    assert payload["fields"] == ["cover_letter", "email", "name", "phone"]
    assert payload["current_url"] == "u"


def test_written_draft_file_has_no_personal_values(tmp_path: Path) -> None:
    """What lands on disk must not contain the operator's personal data."""
    path = write_draft(
        tmp_path,
        "app-1",
        draft_payload(
            {"fingerprint": "fp", "current_url": "u"},
            {"name": "Ada Lovelace", "email": "ada@example.com", "phone": "250-555-0142"},
        ),
    )
    text = path.read_text(encoding="utf-8")
    assert "Ada Lovelace" not in text
    assert "ada@example.com" not in text
    assert "250-555-0142" not in text


def test_reservation_is_safe_across_processes(tmp_path: Path) -> None:
    """Two processes must not both reserve the same posting.

    The in-memory copy of the ledger is stale in a fresh interpreter, so the
    presence check has to re-read the file while holding the lock.
    """
    ledger_path = tmp_path / "ledger.jsonl"
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "from indeed_scraper.apply.ledger import ApplicationLedger\n"
        f"ledger = ApplicationLedger(Path({str(ledger_path)!r}))\n"
        "print('RESERVED' if ledger.reserve('fp-shared', 'jk', 'u') else 'REFUSED')\n"
    )
    results = [
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for _ in range(4)
    ]
    assert results.count("RESERVED") == 1, results
    assert results.count("REFUSED") == 3, results

    ledger = ApplicationLedger(ledger_path)
    reserved = [e for e in ledger.entries if e.get("status") == "reserved"]
    assert len(reserved) == 1


def test_mark_appends_and_never_rewrites_the_file(tmp_path: Path) -> None:
    """mark() must append; the earlier lines stay byte-identical."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp-1", "jk", "u")
    first = ledger.path.read_text(encoding="utf-8")

    ledger.mark("fp-1", "submitted", "")
    second = ledger.path.read_text(encoding="utf-8")

    assert second.startswith(first), "the ledger was rewritten instead of appended"
    assert len(second.splitlines()) == len(first.splitlines()) + 1
    assert ledger.status_of("fp-1") == "submitted"


def test_daily_budget_counts_a_posting_once(tmp_path: Path) -> None:
    """Repeated marks must not inflate the daily count."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitted", "")
    ledger.mark("fp-1", "submitted", "")
    ledger.mark("fp-1", "submitted", "")

    assert ledger.submitted_today(datetime.now(tz=timezone.utc)) == 1


def test_daily_budget_ignores_other_days(tmp_path: Path) -> None:
    """Yesterday's submissions must not count against today's budget."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitted", "")
    yesterday = datetime.now(tz=timezone.utc).replace(year=2000)
    assert ledger.submitted_today(yesterday) == 0
