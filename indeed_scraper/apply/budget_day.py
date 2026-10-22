"""The operator's budget day.

The daily application budget is a promise to the OPERATOR: "at most N
applications per day". The old implementation compared the UTC date of a
submission with the UTC date of "now", so the boundary fell at UTC midnight.

That is not the operator's day. For an operator in Reykjavik (UTC+0) or
Vancouver (UTC-8), UTC midnight falls at 00:00 or 16:00 local, so the
count for "today" was wrong for most of the evening, and a submission made
just before UTC midnight did not consume the quota the operator thought it
had.

The rule:

* the budget day is the LOCAL day of the ``now`` moment. A submission belongs
  to the same budget day as ``now`` when the two fall on the same calendar
  day in ``now``'s own timezone;
* the ``now`` argument already carries a timezone, so no new configuration
  and no new environment variable is needed - the caller's ``now`` decides;
* a naive ``now`` (no timezone) has no local day, so UTC is the documented
  fallback.

This lives in its own module so ``apply/ledger.py`` stays inside the 250-line
house rule.
"""

from __future__ import annotations

from datetime import datetime, timezone


def budget_day(moment: datetime) -> datetime.date:
    """The calendar day *moment* falls on, in *moment*'s own timezone.

    A naive moment is treated as UTC, which is the documented fallback.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc).date()
    return moment.date()


def same_budget_day(when: datetime, now: datetime) -> bool:
    """True when *when* and *now* fall on the same budget day.

    Both timestamps are converted into ``now``'s timezone first, so the
    comparison follows the OPERATOR's day rather than UTC's.
    """
    tz = now.tzinfo if now.tzinfo is not None else timezone.utc
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(tz).date() == now.astimezone(tz).date()
