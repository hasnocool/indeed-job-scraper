"""Risk budget pacing for apply throttling.

The budget is the guard rail that keeps an apply run from behaving like a
bot: a ceiling on how many applications may leave per day, and a minimum
pause between two of them. Both rules fail CLOSED, because a guard rail
that silently turns itself off is worse than no guard rail at all - the
operator believes they are protected when they are not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from indeed_scraper.apply.ledger import ApplicationLedger


@dataclass(frozen=True, slots=True)
class RiskBudget:
    """Pacing constraints for daily apply limits."""

    max_per_day: int = 2
    min_delay_minutes: float = 30.0
    stop_on_captcha: bool = True

    def can_apply(self, ledger: ApplicationLedger, now: datetime | None = None) -> bool:
        """Return False when the daily limit has been reached.

        A NON-POSITIVE ``max_per_day`` BLOCKS every application. It used to
        return True ("no limit"), so a misconfigured cap - a zero from an
        empty environment variable, or a negative value from a bad
        argument - silently disabled the daily budget altogether and let the
        run fire at will. Failing closed is the only safe reading of "at
        most N per day" when N is not a usable N.

        ``max_per_day=None`` still means "no ceiling": it is the explicit
        "the operator chose not to limit this run" value, which is a
        different thing from a broken number.
        """
        if self.max_per_day is None:
            return True
        if self.max_per_day <= 0:
            return False
        return ledger.submitted_today(now) < self.max_per_day

    def delay_seconds(self, last_submit: datetime | None, now: datetime | None = None) -> float:
        """Seconds still to wait based on min_delay_minutes since last submit.

        ``now=None`` means "use the current time". The old code wrote
        ``datetime.now(datetime.timezone.utc)``, but ``datetime`` here is the
        CLASS, and a class has no ``timezone`` attribute - so the very
        branch the CLI reaches on the second application raised
        ``AttributeError`` and the run crashed.

        A naive ``last_submit`` is accepted: it is read as UTC, which is
        what the ledger writes, and comparing a naive stamp with an aware
        clock would raise ``TypeError`` instead.
        """
        if last_submit is None:
            return 0.0
        if now is None:
            now = datetime.now(timezone.utc)
        if last_submit.tzinfo is None:
            last_submit = last_submit.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        elapsed = (now - last_submit).total_seconds()
        minimum = self.min_delay_minutes * 60.0
        remaining = minimum - elapsed
        return max(0.0, remaining)

    @classmethod
    def from_policy(cls, max_per_day: int, min_delay_minutes: float) -> RiskBudget:
        """The operator's policy, with the environment able to TIGHTEN it.

        The policy file is the ceiling. The environment may lower the daily
        cap or raise the delay for one run, and may not raise the cap or
        shorten the delay.
        """
        return cls.config_from_env(
            cls(max_per_day=max_per_day, min_delay_minutes=min_delay_minutes)
        )

    @classmethod
    def config_from_env(cls, ceiling: RiskBudget | None = None) -> RiskBudget:
        """Read the budget from the environment, ignoring unusable values.

        With a ``ceiling``, the environment can only make the budget
        STRICTER: it may lower the daily cap and raise the delay, never
        raise the cap or shorten the delay. That mirrors the command-line
        flags, and it keeps the operator's policy file the ceiling.

        Without a ``ceiling`` the environment value is used as it stands,
        and an unusable value falls back to the class defaults.
        """
        base = ceiling if ceiling is not None else cls()
        max_per_day = base.max_per_day
        min_delay = base.min_delay_minutes

        raw = os.environ.get("INDEED_MAX_APPS_PER_DAY", "").strip()
        if raw:
            try:
                parsed = int(raw)
            except ValueError:
                parsed = None
            if parsed is not None and parsed >= 0:
                if ceiling is None:
                    max_per_day = parsed
                else:
                    max_per_day = min(base.max_per_day, parsed)

        raw = os.environ.get("INDEED_MIN_DELAY_MINUTES", "").strip()
        if raw:
            try:
                parsed = float(raw)
            except ValueError:
                parsed = None
            if parsed is not None and parsed >= 0:
                if ceiling is None:
                    min_delay = parsed
                else:
                    min_delay = max(base.min_delay_minutes, parsed)

        return cls(max_per_day=max_per_day, min_delay_minutes=min_delay)
