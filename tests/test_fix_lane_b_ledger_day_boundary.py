"""B7 - submitted_today must count the OPERATOR's day, not the UTC day.

The daily budget is a promise to the operator: "at most N applications per
day". The old implementation compared ``when.date()`` (UTC) with
``datetime.now(timezone.utc).date()``, so the boundary was UTC midnight.

That is not the operator's day. For an operator in Reykjavik (UTC+0) or
Vancouver (UTC-7), UTC midnight falls at 16:00 or 17:00 local time, so a
submission at 23:59 UTC belongs to the NEXT local day - the operator's
"day" ended hours ago, and the count for "today" was wrong.

The rule this file pins:

* the day boundary is the operator's LOCAL day, taken from the ``now``
  argument's own timezone;
* a submission at 23:59 and one at 00:30 the next morning are counted
  against the days the OPERATOR experienced, not against UTC.

The ``now`` argument already carries a timezone, so the rule needs no
configuration and no new environment variable: the caller's ``now`` decides.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from indeed_scraper.apply.ledger import ApplicationLedger


def _ledger_with_submission(tmp_path: Path, when: datetime) -> ApplicationLedger:
    """A ledger holding one submission stamped at *when*."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp-1", "jk-1", "u")
    ledger.path.write_text(
        ledger.path.read_text(encoding="utf-8")
        + '{"fingerprint":"fp-1","jk":"jk-1","indeed_url":"u","company":"",'
        f'"title":"T","applied_at":"{when.isoformat()}","status":"submitted",'
        '"detail":""}\n',
        encoding="utf-8",
    )
    return ledger


def test_a_submission_at_2359_local_counts_on_that_local_day(tmp_path: Path) -> None:
    """23:59 local is still 'today' for the operator."""
    tz = ZoneInfo("Atlantic/Reykjavik")
    when = datetime(2026, 3, 1, 23, 59, tzinfo=tz)
    ledger = _ledger_with_submission(tmp_path, when)

    now = datetime(2026, 3, 1, 23, 59, 30, tzinfo=tz)
    assert ledger.submitted_today(now) == 1


def test_a_submission_at_0030_local_counts_on_the_next_local_day(
    tmp_path: Path,
) -> None:
    """00:30 the next morning is 'today', and yesterday's is not."""
    tz = ZoneInfo("Atlantic/Reykjavik")
    yesterday = _ledger_with_submission(
        tmp_path, datetime(2026, 3, 1, 23, 59, tzinfo=tz)
    )
    now = datetime(2026, 3, 2, 0, 30, tzinfo=tz)

    # The 23:59 submission belongs to the 1st, not the 2nd.
    assert yesterday.submitted_today(now) == 0


def test_the_boundary_follows_the_operators_timezone(tmp_path: Path) -> None:
    """The SAME instant is a different day for two operators in two zones.

    This is the whole point: the count must follow the caller's local day.
    A submission at 01:30 UTC on the 2nd is still the 1st in Vancouver
    (17:30 on the 1st, PST), but it is already the 2nd in Reykjavik.
    """
    utc_now = datetime(2026, 3, 2, 2, 0, tzinfo=timezone.utc)
    when = datetime(2026, 3, 2, 1, 30, tzinfo=timezone.utc)

    reykjavik = ZoneInfo("Atlantic/Reykjavik")
    vancouver = ZoneInfo("America/Vancouver")

    # In Reykjavik the submission happened on the 2nd, and so does now.
    ledger = _ledger_with_submission(tmp_path, when)
    assert ledger.submitted_today(utc_now.astimezone(reykjavik)) == 1

    # In Vancouver it is still the 1st for both - so it counts as TODAY.
    assert ledger.submitted_today(utc_now.astimezone(vancouver)) == 1


def test_a_submission_before_the_local_midnight_does_not_count_the_next_day(
    tmp_path: Path,
) -> None:
    """The discriminating case: the UTC rule and the local rule disagree.

    23:59 UTC on the 1st. For an operator in Vancouver (UTC-8 in March) that
    is 15:59 on the 1st local. At 00:30 UTC on the 2nd - which is 16:30 on
    the 1st LOCAL - the operator is still on the 1st, so the submission
    counts as today.

    Under the old UTC rule the 2nd had already started, so the count was
    0 and the operator's daily quota was silently restored.
    """
    vancouver = ZoneInfo("America/Vancouver")
    when = datetime(2026, 3, 1, 23, 59, tzinfo=timezone.utc)
    ledger = _ledger_with_submission(tmp_path, when)

    # 00:30 UTC on the 2nd = 16:30 on the 1st in Vancouver.
    now = datetime(2026, 3, 2, 0, 30, tzinfo=timezone.utc).astimezone(vancouver)
    assert now.date() == when.astimezone(vancouver).date(), "the test setup is wrong"

    assert ledger.submitted_today(now) == 1, (
        "the submission is still on the operator's local day; the old UTC "
        "rule said 0 and silently restored the daily quota"
    )


def test_the_old_utc_behaviour_is_gone(tmp_path: Path) -> None:
    """A UTC-midnight boundary must not decide the count any more.

    23:59 UTC on the 1st, counted at 00:30 UTC on the 2nd: under the old
    rule the submission was already 'yesterday' (UTC), so the operator's
    fresh quota was silently restored.
    """
    when = datetime(2026, 3, 1, 23, 59, tzinfo=timezone.utc)
    ledger = _ledger_with_submission(tmp_path, when)

    now = datetime(2026, 3, 2, 0, 30, tzinfo=timezone.utc)
    # Under the operator's local day (the caller decides), the 2nd is a new
    # day and the 1st's submission does not count against it.
    assert ledger.submitted_today(now) == 0


def test_a_naive_now_is_treated_as_utc(tmp_path: Path) -> None:
    """A naive timestamp has no local day, so UTC is the documented fallback."""
    when = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    ledger = _ledger_with_submission(tmp_path, when)

    assert ledger.submitted_today(datetime(2026, 3, 1, 13, 0)) == 1  # noqa: DTZ001 - naive datetime is the deliberate input; a naive now is treated as UTC


def test_the_count_is_still_one_per_fingerprint(tmp_path: Path) -> None:
    """Repeated marks must not inflate the count."""
    tz = ZoneInfo("Atlantic/Reykjavik")
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.reserve("fp-1", "jk-1", "u")
    ledger.mark("fp-1", "submitted", "")
    ledger.mark("fp-1", "submitted", "")

    # mark() stamps the CURRENT time, so the query must use the current time.
    now = datetime.now(tz=timezone.utc).astimezone(tz)
    assert ledger.submitted_today(now) == 1


def test_todays_submissions_and_yesterdays_do_not_mix(tmp_path: Path) -> None:
    """A submission from yesterday must not consume today's budget."""
    yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
    ledger = _ledger_with_submission(tmp_path, yesterday)

    assert ledger.submitted_today(datetime.now(tz=timezone.utc)) == 0
