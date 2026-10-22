"""C2 + C3: the autonomy policy is a CEILING, and a submit is never automatic.

C2
    ``needs_confirm = confirm and not rules.allows_submit`` meant that at
    ``auto``/``full`` there was NO prompt at all, and the operator's live
    policy file said ``level: "full"`` - so ``python3 -m indeed_scraper
    apply`` would submit REAL applications with no prompt, contradicting
    HC-4 ("no unattended submit").

    The fix: an unattended submit of a REAL application is not reachable by
    a single flag. The policy level says what the run MAY do; a separate,
    explicit operator switch says whether this run is allowed to do it
    unattended. The default for that switch is OFF.

C3
    ``--max-per-day`` and ``--min-delay`` could RAISE the policy file's
    ceiling, even though the docstring said the file is the ceiling. A flag
    may only LOWER the cap (fewer per day, a LONGER delay), never raise it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from indeed_scraper.apply.autonomy import AutonomyPolicy
from indeed_scraper.errors import IndeedScraperError

# ---------------------------------------------------------------------------
# C2: the unattended submit needs a SEPARATE, explicit opt-in
# ---------------------------------------------------------------------------


def test_the_default_policy_is_manual() -> None:
    """A fresh install is conservative, not permissive."""
    policy = AutonomyPolicy()
    assert policy.level == "manual"
    assert policy.max_applications_per_day == 2
    assert policy.min_delay_minutes == 30.0
    assert policy.allow_binding_commitments is False
    assert policy.allows_submit is False
    assert policy.allows_reply is False


def test_a_missing_policy_file_falls_back_to_manual(tmp_path: Path) -> None:
    policy = AutonomyPolicy.load(tmp_path / "nope.json")
    assert policy.level == "manual"
    assert policy.max_applications_per_day == 2
    assert policy.min_delay_minutes == 30.0
    assert policy.allows_submit is False


def test_auto_alone_does_not_allow_an_unattended_submit() -> None:
    """The policy level is a permission, not a decision to submit."""
    assert AutonomyPolicy(level="auto").allows_submit is False
    assert AutonomyPolicy(level="full").allows_submit is False


def test_an_unattended_submit_needs_the_separate_switch() -> None:
    """Only the explicit switch turns the unattended submit on."""
    opted_in = AutonomyPolicy(level="auto", unattended_submit=True)
    assert opted_in.allows_submit is True
    assert AutonomyPolicy(level="manual", unattended_submit=True).allows_submit is False


def test_the_switch_is_not_written_by_an_ordinary_policy_file(tmp_path: Path) -> None:
    """A policy file that does not mention the switch must not enable it."""
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps({"level": "full", "max_applications_per_day": 40}),
        encoding="utf-8",
    )
    policy = AutonomyPolicy.load(path)
    assert policy.level == "full"
    assert policy.unattended_submit is False
    assert policy.allows_submit is False


def test_the_policy_file_can_opt_in_explicitly(tmp_path: Path) -> None:
    """The operator may still choose the unattended run, in writing."""
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps({"level": "auto", "unattended_submit": True}),
        encoding="utf-8",
    )
    policy = AutonomyPolicy.load(path)
    assert policy.unattended_submit is True
    assert policy.allows_submit is True


def test_a_malformed_switch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"level": "auto", "unattended_submit": "yes"}), encoding="utf-8")
    with pytest.raises(IndeedScraperError):
        AutonomyPolicy.load(path)


# ---------------------------------------------------------------------------
# C3: the CLI flags may only LOWER the file's ceiling
# ---------------------------------------------------------------------------


def _write_policy(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_flag_cannot_raise_the_daily_cap(tmp_path: Path) -> None:
    """``--max-per-day 25`` against a file that says 2 stays at 2."""
    from indeed_scraper.cli import _policy

    _write_policy(tmp_path, {"level": "manual", "max_applications_per_day": 2})
    rules = _policy(None, 25, None, policy_path=tmp_path / "policy.json")
    assert rules.max_applications_per_day == 2


def test_a_flag_cannot_shorten_the_delay(tmp_path: Path) -> None:
    """``--min-delay 5`` against a file that says 30 stays at 30."""
    from indeed_scraper.cli import _policy

    _write_policy(tmp_path, {"level": "manual", "min_delay_minutes": 30})
    rules = _policy(None, None, 5, policy_path=tmp_path / "policy.json")
    assert rules.min_delay_minutes == 30.0


def test_a_flag_may_lower_the_daily_cap(tmp_path: Path) -> None:
    from indeed_scraper.cli import _policy

    _write_policy(tmp_path, {"level": "manual", "max_applications_per_day": 10})
    rules = _policy(None, 3, None, policy_path=tmp_path / "policy.json")
    assert rules.max_applications_per_day == 3


def test_a_flag_may_lengthen_the_delay(tmp_path: Path) -> None:
    from indeed_scraper.cli import _policy

    _write_policy(tmp_path, {"level": "manual", "min_delay_minutes": 15})
    rules = _policy(None, None, 90, policy_path=tmp_path / "policy.json")
    assert rules.min_delay_minutes == 90.0


def test_a_flag_cannot_raise_the_autonomy_level(tmp_path: Path) -> None:
    """The file is the ceiling on the LEVEL too."""
    from indeed_scraper.cli import _policy

    _write_policy(tmp_path, {"level": "manual"})
    rules = _policy("full", None, None, policy_path=tmp_path / "policy.json")
    assert rules.level == "manual"


def test_a_flag_cannot_turn_on_the_unattended_switch(tmp_path: Path) -> None:
    """The unattended switch is not reachable through a level flag."""
    from indeed_scraper.cli import _policy

    _write_policy(tmp_path, {"level": "manual"})
    rules = _policy("full", None, None, policy_path=tmp_path / "policy.json")
    assert rules.unattended_submit is False
    assert rules.allows_submit is False


# ---------------------------------------------------------------------------
# C6: a malformed policy file is an operator message, not a traceback
# ---------------------------------------------------------------------------


def test_a_malformed_daily_cap_is_an_operator_message(tmp_path: Path) -> None:
    path = _write_policy(tmp_path, {"level": "manual", "max_applications_per_day": "lots"})
    with pytest.raises(IndeedScraperError) as error:
        AutonomyPolicy.load(path)
    message = str(error.value)
    assert "max_applications_per_day" in message
    assert str(path) in message


def test_a_malformed_delay_is_an_operator_message(tmp_path: Path) -> None:
    path = _write_policy(tmp_path, {"level": "manual", "min_delay_minutes": "soon"})
    with pytest.raises(IndeedScraperError) as error:
        AutonomyPolicy.load(path)
    message = str(error.value)
    assert "min_delay_minutes" in message
    assert str(path) in message


def test_a_malformed_level_is_an_operator_message(tmp_path: Path) -> None:
    path = _write_policy(tmp_path, {"level": 7})
    with pytest.raises(IndeedScraperError) as error:
        AutonomyPolicy.load(path)
    assert str(path) in str(error.value)
