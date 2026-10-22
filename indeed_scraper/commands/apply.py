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
    - a posting SKIPPED because it was already applied to or reserved -> 0
    - blocked by a challenge (CAPTCHA / auth wall) -> 3
    - nothing submitted and at least one attempt failed -> 2

    Any status that is not ``"submitted"`` counts as a non-submitted
    outcome, so results from other lanes (e.g. ``"unconfirmed"``) never
    masquerade as success.

    A SKIP is not a failure. The run did what it was asked: it left a
    posting it had already applied to alone. Reporting that as "failed"
    made the exit code say "an attempt failed" for a run that did exactly
    the right thing - and the operator's tooling acted on it.
    """
    if not results:
        return 0
    # The CHALLENGE check comes FIRST. The flow BREAKS on a challenge, so
    # "[submitted, blocked]" is the production shape: a run that submitted
    # one application and was then stopped by a wall. The "any submitted"
    # check fired first and returned 0, so CI read "all good" for a run
    # that was stopped by Indeed's bot protection. The operator saw it on
    # the console; the exit code is what the tooling reads.
    if any(
        result.status == "blocked" and "challenge" in (result.detail or "")
        for result in results
    ):
        return 3
    if any(result.status == "submitted" for result in results):
        return 0
    if any(result.status == "skipped" for result in results) and all(
        result.status in {"submitted", "skipped"} for result in results
    ):
        # A run that only skipped postings is not a failed run.
        return 0
    if dry_run and all(
        result.status == "failed" and result.detail == "dry_run"
        for result in results
    ):
        return 0
    return 2
