"""Wave 2 — the daily budget, and the pacing that holds ACROSS runs.

**N2 MAJOR.** The rule "an unconfirmed attempt consumes a slot of the
daily budget" was right but had no test stating it. Only an integration
test happened to touch it, and that gap is exactly why the budget hole
survived a whole lane: the rule had no name of its own, so nothing
referred to it and nothing broke when it was broken.

**U2 MAJOR.** The minimum delay between two submissions was applied only
WITHIN one run. ``last_submit`` started as ``None`` on every invocation,
so two back-to-back runs submitted with zero spacing between them. The
30-minute pacing is the whole point of the risk budget, and it has to hold
across invocations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.risk import RiskBudget

# ---------------------------------------------------------------------------
# N2 — the rule, stated directly
# ---------------------------------------------------------------------------

def test_an_unconfirmed_attempt_consumes_a_slot_of_the_daily_budget(
    tmp_path: Path,
) -> None:
    """An UNCONFIRMED attempt counts against the daily budget.

    The submit click may have reached the employer even though the
    confirmation could not be read. The operator cannot un-send it, so the
    budget has to assume it went out.

    This test states the rule directly, so the rule has a name of its own
    and a change to it breaks something on purpose.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=1)

    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "unconfirmed", "submit_unconfirmed")

    assert ledger.submitted_today() == 1, (
        "an unconfirmed attempt must consume a slot of the daily budget"
    )
    assert budget.can_apply(ledger) is False, (
        "the budget must be exhausted by an unconfirmed attempt"
    )


def test_a_confirmed_attempt_consumes_a_slot_of_the_daily_budget(
    tmp_path: Path,
) -> None:
    """The obvious case, pinned next to the surprising one."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=1)

    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "submitted", "")

    assert ledger.submitted_today() == 1
    assert budget.can_apply(ledger) is False


def test_a_failed_attempt_does_not_consume_a_slot(tmp_path: Path) -> None:
    """A failed attempt consumed nothing, so it must not consume a slot.

    The rule counts attempts that MAY have reached the employer. A form
    that was never submitted reached nobody.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=1)

    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "failed", "submit_not_found")

    assert ledger.submitted_today() == 0
    assert budget.can_apply(ledger) is True


# ---------------------------------------------------------------------------
# U2 — the pacing holds across runs
# ---------------------------------------------------------------------------

def test_the_ledger_knows_when_the_last_submission_happened(tmp_path: Path) -> None:
    """The ledger must be able to say when the last submission went out.

    Without this the flow cannot pace itself across invocations: it only
    ever knew about the submissions made during the current run.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "submitted", "")

    last = ledger.last_submit_time()

    assert last is not None, "the ledger must report the last submission time"
    assert isinstance(last, datetime)
    # The timestamp is written by the ledger itself, so it must be close
    # to now - not an hour in the past, not in the future.
    drift = abs((datetime.now(tz=timezone.utc) - last).total_seconds())
    assert drift < 60, f"the reported time is {drift}s away from now"


def test_an_unconfirmed_attempt_also_reports_its_time(tmp_path: Path) -> None:
    """An unconfirmed attempt went out too, so it paces the next one.

    It may already have reached the employer. Pacing only after a
    CONFIRMED submission would let an unconfirmed one slip through
    un-paced, and unconfirmed attempts are exactly the ones that went out
    without anybody noticing.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "unconfirmed", "submit_unconfirmed")

    assert ledger.last_submit_time() is not None


def test_an_empty_ledger_reports_no_last_submission(tmp_path: Path) -> None:
    """Nothing was submitted, so there is nothing to pace against."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    assert ledger.last_submit_time() is None


def test_the_most_recent_submission_wins(tmp_path: Path) -> None:
    """The pacing must use the NEWEST submission, not the oldest."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "submitted", "")
    first = ledger.last_submit_time()
    assert first is not None

    assert ledger.reserve("fp-2", "jk", "u")
    ledger.mark("fp-2", "submitting", "")
    ledger.mark("fp-2", "submitted", "")
    second = ledger.last_submit_time()

    assert second is not None
    assert second >= first, "the ledger must report the newest submission"


def test_two_sequential_runs_respect_the_delay(tmp_path: Path) -> None:
    """The 30-minute minimum delay must hold ACROSS two runs.

    Before the fix ``last_submit`` started as ``None`` in every run, so
    the second invocation submitted with ZERO spacing after the first.
    The delay is the risk budget's whole point, and it has to survive the
    end of a process.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=5, min_delay_minutes=30.0)

    # --- run one -----------------------------------------------------
    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "submitted", "")

    # --- run two: a FRESH process, reading the same ledger -----------
    second_ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    last_submit = second_ledger.last_submit_time()
    assert last_submit is not None, (
        "the second run must be able to read when the first run submitted"
    )

    wait = budget.delay_seconds(last_submit)
    assert wait > 0, (
        f"the second run must wait before submitting, waited {wait}s"
    )
    assert wait >= 29 * 60, f"the wait must be the full 30 minutes, got {wait}s"


def test_the_delay_does_not_apply_to_a_ledger_that_never_submitted(
    tmp_path: Path,
) -> None:
    """Nothing was sent, so nothing has to be waited for."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=5, min_delay_minutes=30.0)

    assert budget.delay_seconds(ledger.last_submit_time()) == 0.0


def test_a_stale_submission_does_not_block_forever(tmp_path: Path) -> None:
    """A submission from long ago must not pause a run for 30 minutes.

    The delay is a pacing rule, not a lock: once the minimum gap has
    passed, the next application may go out.
    """
    budget = RiskBudget(max_per_day=5, min_delay_minutes=30.0)
    old = datetime.now(tz=timezone.utc) - timedelta(hours=3)

    assert budget.delay_seconds(old) == 0.0
