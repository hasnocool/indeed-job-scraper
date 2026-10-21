"""Risk budget pacing for apply throttling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from indeed_scraper.apply.ledger import ApplicationLedger


@dataclass(frozen=True, slots=True)
class RiskBudget:
    """Pacing constraints for daily apply limits."""

    max_per_day: int = 2
    min_delay_minutes: float = 30.0
    stop_on_captcha: bool = True

    def can_apply(self, ledger: ApplicationLedger, now: datetime | None = None) -> bool:
        """Return False when daily limit has been reached."""
        if self.max_per_day is None or self.max_per_day <= 0:
            return True
        return ledger.submitted_today(now) < self.max_per_day

    def delay_seconds(self, last_submit: datetime | None, now: datetime | None = None) -> float:
        """Seconds still to wait based on min_delay_minutes since last submit."""
        if last_submit is None:
            return 0.0
        if now is None:
            now = datetime.now(datetime.timezone.utc)
        elapsed = (now - last_submit).total_seconds()
        minimum = self.min_delay_minutes * 60.0
        remaining = minimum - elapsed
        return max(0.0, remaining)

    @classmethod
    def config_from_env(cls) -> RiskBudget:
        """Read from env vars, fall back to defaults; ignores bad values."""
        try:
            val = os.environ.get("INDEED_MAX_APPS_PER_DAY")
            max_per_day = int(val) if val and val.isdigit() else cls.__dataclass_fields__["max_per_day"].default
        except (ValueError, TypeError):
            max_per_day = cls.__dataclass_fields__["max_per_day"].default

        try:
            val = os.environ.get("INDEED_MIN_DELAY_MINUTES")
            min_delay = float(val) if val else cls.__dataclass_fields__["min_delay_minutes"].default
        except (ValueError, TypeError):
            min_delay = cls.__dataclass_fields__["min_delay_minutes"].default

        return cls(max_per_day=max_per_day, min_delay_minutes=min_delay)