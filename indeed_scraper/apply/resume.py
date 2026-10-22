"""Resume an interrupted application, with the same idempotency guard as apply.

The apply path (``apply/worker.py``) reserves the posting in the ledger
BEFORE the browser is touched and marks it ``submitting`` BEFORE the
irreversible submit click. That pair is what makes the invariant "at most ONE
submission per fingerprint, ever" hold: a run killed in the instant after the
click leaves a live status behind, so the next run refuses the posting.

The resume path used to do NEITHER. A kill after the click left an EMPTY
ledger, the posting looked untouched, and a second ``resume`` submitted it
again. This module restores the invariant for the resume path.

The logic lives here rather than in ``apply/flow.py`` so that file stays
inside the 250-line house rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console

from ..config import Config
from ..cookies import CookieStore
from . import indeed_form
from .autonomy import AutonomyPolicy
from .drafts import draft_payload, read_draft, write_draft
from .driver import open_driver
from .exceptions import ApplyBlockedError, FieldMissingError
from .flow import _stale
from .ledger import ApplicationLedger
from .profile import Profile, validate_resume
from .risk import RiskBudget
from .types import ApplyResult
from .workspace import drafts_dir


def _resume_result(
    draft: dict[str, Any],
    *,
    app_id: str,
    url: str,
    fingerprint: str,
    status: str,
    detail: str,
) -> ApplyResult:
    """Build the outcome of a resume from the draft's metadata."""
    return ApplyResult(
        jk=str(draft.get("jk", "")),
        title=str(draft.get("title", "")),
        company=str(draft.get("company", "")),
        location=str(draft.get("location", "")),
        url=url,
        fingerprint=fingerprint,
        app_id=app_id,
        status=status,
        portal="indeed",
        detail=detail,
    )


def resume_application(
    config: Config,
    store: CookieStore,
    console: Console,
    app_id: str,
    *,
    profile: Profile,
    confirm: bool = True,
    dry_run: bool = False,
    risk_budget: RiskBudget | None = None,
    policy: AutonomyPolicy | None = None,
) -> ApplyResult | None:
    """Resume an interrupted application from its persisted draft.

    The ledger is the idempotency guard, and the resume path obeys the same
    rules as the apply path:

    1. a posting whose latest status is LIVE (reserved / submitting /
       submitted / unconfirmed) is NEVER resumed - the previous attempt may
       have gone out, and a duplicate application is worse than a missed one;
    2. the posting is RESERVED in the ledger BEFORE the browser is touched,
       so a concurrent run cannot slip in between;
    3. ``submitting`` is marked BEFORE the irreversible click, so a kill in
       that window leaves a live status and the posting stays blocked;
    4. a ``submitted`` status is recorded ONLY when the submit control
       reported a real confirmation signal.
    """
    session = store.current()
    if session is None or not session.is_signed_in():
        raise ApplyBlockedError("no-session", "")

    draft = read_draft(drafts_dir(config), app_id)
    if not draft:
        console.print(f"[yellow]No draft found for {app_id}.[/yellow]")
        return None

    ledger = ApplicationLedger(config.state_dir / "applications" / "ledger.jsonl")
    fingerprint = str(draft.get("fingerprint", ""))
    url = str(draft.get("current_url", ""))
    if not url:
        console.print("[yellow]Draft has no URL to resume from.[/yellow]")
        return None

    rules = policy or AutonomyPolicy()
    budget = risk_budget or RiskBudget.from_policy(
        rules.max_applications_per_day,
        rules.min_delay_minutes,
    )
    needs_confirm = confirm and not rules.allows_submit
    validate_resume(Path(profile.resume_path).expanduser())
    if not dry_run and not budget.can_apply(ledger):
        console.print("[yellow]daily application budget reached - not resuming.[/yellow]")
        return None

    # Idempotency guard: a posting that already reached a live state must
    # never be re-submitted by a resume. The decision comes from the
    # SHARED helper in apply/flow.py, so the apply path and the resume path
    # can never drift apart, and LIVE_STATUSES is the ledger's own
    # definition rather than a set re-derived here.
    if fingerprint:
        previous = ledger.status_of(fingerprint)
        if previous == "reserved" and _stale(ledger, fingerprint):
            # A previous run was killed BEFORE the submit click: release the
            # stale reservation so the posting is not blocked for ever. This
            # mirrors the apply path (apply/flow.py).
            ledger.mark(fingerprint, "failed", "stale_reservation_released")
            console.print(f"[dim]released a stale reservation for {app_id}[/dim]")
            previous = None
        if previous in ApplicationLedger.LIVE_STATUSES:
            if previous == "submitted":
                console.print(
                    f"[yellow]{app_id} is already submitted - not resuming.[/yellow]"
                )
            else:
                console.print(
                    f"[yellow]{app_id} is already {previous} - not resuming.[/yellow]"
                )
            return None

        # Reserve BEFORE the browser is touched. reserve() is atomic and
        # refuses a fingerprint that is already live, so this is the same
        # guard the apply path uses - not a second, weaker one.
        reserved = ledger.reserve(
            fingerprint=fingerprint,
            jk=str(draft.get("jk", "")),
            indeed_url=url,
            company=str(draft.get("company", "")),
            title=str(draft.get("title", "")),
        )
        if not reserved:
            # Another run reserved it between our check and this call.
            console.print(f"[yellow]{app_id} is already reserved - not resuming.[/yellow]")
            return None

    with open_driver(config, session) as (context, info):
        console.print(f"[dim]driver: {info.kind} ({info.endpoint})[/dim]")
        existing_pages = list(context.pages)
        page = existing_pages[0] if existing_pages else context.new_page()
        owns_page = not existing_pages
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=config.navigation_timeout_ms)
            page.wait_for_timeout(2000)
            challenge = indeed_form.detect_challenge(page)
            if challenge:
                ledger.mark(fingerprint, "blocked", f"challenge:{challenge}")
                raise ApplyBlockedError(challenge, url)
            # The same portal guard the apply path applies. The selectors
            # in this module were written for Indeed's own form, so
            # resuming into an external ATS would fill the wrong fields
            # and submit them.
            #
            # An external destination is a PER-POSTING block, exactly as
            # it is on the apply path: the posting is marked blocked and
            # the run carries on. Only a challenge stops the whole run.
            reason = _portal_reason(page)
            if reason:
                ledger.mark(fingerprint, "blocked", reason)
                console.print(
                    f"[yellow]resume {app_id} blocked - {reason}[/yellow]"
                )
                return None
            try:
                filled = indeed_form.fill_indeed_form(page, profile)
            except FieldMissingError as error:
                # A required field is missing or the form is empty: block the
                # posting so it is not retried silently.
                ledger.mark(fingerprint, "blocked", f"missing:{error.question}")
                console.print(f"[yellow]resume {app_id} blocked - missing: {error.question}[/yellow]")
                return None
            write_draft(drafts_dir(config), app_id, draft_payload(draft, filled))
            if dry_run:
                # A rehearsal must leave an honest trace: release the
                # reservation and report the real status, so the operator is
                # not told the posting is still reserved.
                ledger.mark(fingerprint, "failed", "dry_run_resume")
                console.print("[cyan]dry-run[/cyan] resumed fill, not submitted")
                return _resume_result(
                    draft,
                    app_id=app_id,
                    url=url,
                    fingerprint=fingerprint,
                    status="failed",
                    detail="dry_run_resume",
                )
            if needs_confirm:
                console.print("[bold]Submit the resumed application?[/bold]")
                if not console.input("[yellow]type 'yes' to submit: [/yellow]").strip().lower().startswith("y"):
                    ledger.mark(fingerprint, "failed", "operator_declined")
                    return None

            # The submission is recorded as ATTEMPTED before the irreversible
            # click. If the run dies between here and the confirmation, the
            # ledger still shows the attempt, so the posting is never applied
            # to a second time.
            ledger.mark(fingerprint, "submitting", "")

            result = indeed_form.submit_application(page)
            if result.confirmed:
                ledger.mark(fingerprint, "submitted", "")
                console.print(f"[green]submitted[/green] resumed application {app_id}")
                return _resume_result(
                    draft,
                    app_id=app_id,
                    url=url,
                    fingerprint=fingerprint,
                    status="submitted",
                    detail="",
                )
            if result.clicked:
                # The control was clicked but no confirmation was observed.
                # The posting is left BLOCKED: it may have gone out, and a
                # second attempt would be a duplicate application.
                ledger.mark(fingerprint, "unconfirmed", "submit_unconfirmed")
                console.print(
                    f"[yellow]{app_id} was submitted but not confirmed - "
                    "check Indeed before applying again[/yellow]"
                )
                return _resume_result(
                    draft,
                    app_id=app_id,
                    url=url,
                    fingerprint=fingerprint,
                    status="unconfirmed",
                    detail="submit_unconfirmed",
                )
            ledger.mark(fingerprint, "failed", "submit_not_found")
            console.print(f"[red]{app_id} - no submit control found[/red]")
            return _resume_result(
                draft,
                app_id=app_id,
                url=url,
                fingerprint=fingerprint,
                status="failed",
                detail="submit_not_found",
            )
        finally:
            # Close the tab only if this flow opened it, so a challenge page is
            # never left open in the shared browser.
            if owns_page:
                page.close()


def _portal_reason(page: Any) -> str:
    """Why this destination cannot be resumed into, or "" when it can.

    The apply path calls ``detect_portal`` and refuses an external ATS
    ("external") or an unrecognised page ("unknown"). The resume path did
    not, so it would fill and submit on a greenhouse page - a site whose
    form these selectors were never written against.

    Returns:
        "" when the destination is an Indeed form, otherwise the reason
        the posting is blocked (the same words the apply path uses).
    """
    portal = indeed_form.detect_portal(page)
    if portal == "indeed":
        return ""
    return "external_portal_deferred" if portal == "external" else "unknown_portal"
