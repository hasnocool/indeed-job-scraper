"""Operator autonomy policy: how much the agent may do without asking.

The policy replaces a hard-coded "always confirm" with an explicit, operator-owned
setting, so an unattended run is a deliberate choice rather than a hole in the
safety machinery.

Levels
------
``manual``
    Every submission is confirmed by the operator. Replies are never sent.
``auto``
    Submissions MAY happen without a prompt, inside the risk budget. Replies
    are still drafted for the operator.
``full``
    Submissions and replies MAY be sent without a prompt, inside the risk
    budget.

The level is a PERMISSION, not a decision. An unattended submit of a real
application also needs the separate ``unattended_submit`` switch, which is
OFF by default and is only enabled by writing it in the policy file. That
matters because the level alone used to be enough: with a policy file saying
``"level": "full"`` the operator's real applications went out with no prompt
at all, which is exactly what HC-4 forbids. A flag can never turn the switch
on - only the operator's own policy file can.

One thing stays gated in every level unless the operator explicitly opts in:
a reply that ACCEPTS an offer or agrees to contractual terms. That is a binding
commitment made on the operator's behalf, and ``allow_binding_commitments``
must be set for it to be automated.

The policy lives in ``~/.config/indeed_scraper/policy.json`` (0600, outside the
repository) and can be overridden with ``INDEED_AUTONOMY``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..errors import IndeedScraperError

AutonomyLevel = Literal["manual", "auto", "full"]

LEVELS: tuple[AutonomyLevel, ...] = ("manual", "auto", "full")
POLICY_ENV = "INDEED_AUTONOMY"
POLICY_FILENAME = "policy.json"


def _coerce_int(value: Any, key: str, path: Path) -> int:
    """Coerce a policy value to int, or fail with an operator-facing message."""
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise IndeedScraperError(
            f"Invalid {key} {value!r} in policy file {path}: must be a whole number"
        ) from error


def _coerce_float(value: Any, key: str, path: Path) -> float:
    """Coerce a policy value to float, or fail with an operator-facing message."""
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise IndeedScraperError(
            f"Invalid {key} {value!r} in policy file {path}: must be a number"
        ) from error


def _coerce_bool(value: Any, key: str, path: Path) -> bool:
    """Coerce a policy value to bool; anything but a real true/false is rejected."""
    if isinstance(value, bool):
        return value
    raise IndeedScraperError(
        f"Invalid {key} {value!r} in policy file {path}: must be true or false"
    )


def policy_path() -> Path:
    """Where the policy file lives."""
    override = os.environ.get("INDEED_POLICY_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "indeed_scraper" / POLICY_FILENAME


@dataclass(frozen=True, slots=True)
class AutonomyPolicy:
    """What the agent may do without the operator's approval."""

    level: AutonomyLevel = "manual"
    max_applications_per_day: int = 2
    min_delay_minutes: float = 30.0
    allow_binding_commitments: bool = False
    unattended_submit: bool = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> AutonomyPolicy:
        """Build a policy from the environment alone (safe defaults)."""
        level = os.environ.get(POLICY_ENV, "").strip().lower()
        if level and level not in LEVELS:
            raise IndeedScraperError(
                f"{POLICY_ENV}={level!r} is not one of {', '.join(LEVELS)}"
            )
        return cls(level=level or "manual")

    @classmethod
    def load(cls, path: Path | None = None) -> AutonomyPolicy:
        """Load the policy file, falling back to the environment.

        A missing file is not an error: the defaults are deliberately
        conservative, so a fresh install is safe.
        """
        target = path or policy_path()
        if not target.is_file():
            return cls.from_env()
        try:
            raw = target.read_text(encoding="utf-8")
        except OSError as error:
            raise IndeedScraperError(
                f"Cannot read the policy file {target}: {error}. "
                "Fix its permissions, or remove it to fall back to the "
                "conservative default."
            ) from error
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            raise IndeedScraperError(
                f"Invalid JSON in policy file {target}: {error}"
            ) from error
        if not isinstance(data, dict):
            raise IndeedScraperError(f"Policy file {target} must contain an object")
        level = str(data.get("level", "manual")).strip().lower()
        if level not in LEVELS:
            raise IndeedScraperError(
                f"Policy level {level!r} in {target} is not one of {', '.join(LEVELS)}"
            )
        max_applications_per_day = _coerce_int(
            data.get("max_applications_per_day", 2), "max_applications_per_day", target
        )
        min_delay_minutes = _coerce_float(
            data.get("min_delay_minutes", 30.0), "min_delay_minutes", target
        )
        allow_binding_commitments = _coerce_bool(
            data.get("allow_binding_commitments", False),
            "allow_binding_commitments",
            target,
        )
        unattended_submit = _coerce_bool(
            data.get("unattended_submit", False), "unattended_submit", target
        )
        return cls(
            level=level,  # type: ignore[arg-type]
            max_applications_per_day=max_applications_per_day,
            min_delay_minutes=min_delay_minutes,
            allow_binding_commitments=allow_binding_commitments,
            unattended_submit=unattended_submit,
        )

    def save(self, path: Path | None = None) -> Path:
        """Write the policy file atomically at 0600."""
        target = path or policy_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        tmp = target.with_suffix(".tmp")
        payload = {
            "level": self.level,
            "max_applications_per_day": self.max_applications_per_day,
            "min_delay_minutes": self.min_delay_minutes,
            "allow_binding_commitments": self.allow_binding_commitments,
            "unattended_submit": self.unattended_submit,
        }
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        os.replace(tmp, target)
        return target

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    @property
    def allows_submit(self) -> bool:
        """True when a submission needs no prompt.

        The policy level is only a permission: an unattended submit also
        requires the explicit ``unattended_submit`` switch.
        """
        return self.level in {"auto", "full"} and self.unattended_submit

    @property
    def allows_reply(self) -> bool:
        """True when a reply needs no prompt."""
        return self.level == "full"

    @property
    def allows_binding_commitment(self) -> bool:
        """True when an offer-accepting reply may be sent unattended."""
        return self.allow_binding_commitments

    def restrict_to(self, level: AutonomyLevel) -> AutonomyPolicy:
        """Return a policy that is no more autonomous than this one.

        The policy FILE is the operator's standing decision and therefore
        the ceiling: a command-line flag or an environment variable can
        lower the autonomy for one run, but never raise it above what the
        operator allowed in the file.
        """
        order = ("manual", "auto", "full")
        if order.index(level) >= order.index(self.level):
            return self
        return AutonomyPolicy(
            level=level,
            max_applications_per_day=self.max_applications_per_day,
            min_delay_minutes=self.min_delay_minutes,
            allow_binding_commitments=self.allow_binding_commitments,
            unattended_submit=self.unattended_submit,
        )

    def describe(self) -> str:
        """A one-line human summary.

        The unattended-submit switch is shown explicitly because it is the
        difference between "the operator is asked" and "a real application
        goes out with no prompt" - the operator must be able to see it.
        """
        return (
            f"level={self.level} "
            f"max/day={self.max_applications_per_day} "
            f"min_delay={self.min_delay_minutes}m "
            f"binding_commitments={'auto' if self.allow_binding_commitments else 'gated'} "
            f"unattended_submit={'ON' if self.unattended_submit else 'off'}"
        )
