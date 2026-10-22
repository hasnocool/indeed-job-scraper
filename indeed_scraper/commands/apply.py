"""Exit codes for the ``apply`` command.

The exit code is the machine-readable signal: it tells an automated caller
whether something was actually submitted, everything failed, or the run was
blocked by a challenge.
"""

from __future__ import annotations

from indeed_scraper.apply.types import ApplyResult


def exit_code_for(results: list[ApplyResult], dry_run: bool = False) -> int:
    """Translate apply outcomes into a process exit code.

    - anything submitted -> 0
    - a dry run that did exactly what it was asked -> 0
    - nothing to apply to -> 0
    - blocked by a challenge (CAPTCHA / auth wall) -> 3
    - nothing submitted and at least one attempt failed -> 2

    Any status that is not ``"submitted"`` counts as a non-submitted
    outcome, so results from other lanes (e.g. ``"unconfirmed"``) never
    masquerade as success.
    """
    if not results:
        return 0
    if any(result.status == "submitted" for result in results):
        return 0
    if dry_run and all(
        result.status == "failed" and result.detail == "dry_run"
        for result in results
    ):
        return 0
    if any(
        result.status == "blocked" and "challenge" in (result.detail or "")
        for result in results
    ):
        return 3
    return 2
