"""The per-posting worker: one guarded attempt at a single job."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from ..config import Config
from ..scraper import Job
from .drafts import app_id_for, draft_payload, write_draft
from .exceptions import ApplyBlockedError, FieldMissingError
from .ledger import ApplicationLedger
from .profile import Profile
from .types import ApplyResult, ApplyStatus, PortalType
from .workspace import drafts_dir


def _result(
    job: Job,
    fingerprint: str,
    status: ApplyStatus,
    portal: str,
    detail: str = "",
) -> ApplyResult:
    return ApplyResult(
        jk=job.jk,
        title=job.title,
        company=job.company,
        location=job.location,
        url=job.url,
        fingerprint=fingerprint,
        app_id=app_id_for(fingerprint),
        status=status,
        portal=portal,  # type: ignore[arg-type]
        detail=detail,
    )


def _apply_one(
    page: Any,
    job: Job,
    fingerprint: str,
    profile: Profile,
    ledger: ApplicationLedger,
    config: Config,
    console: Console,
    *,
    confirm: bool,
    dry_run: bool,
) -> ApplyResult:
    """Run the guarded sequence for one posting. Returns its outcome."""
    from . import indeed_form

    if not ledger.reserve(
        fingerprint=fingerprint,
        jk=job.jk,
        indeed_url=job.url,
        company=job.company,
        title=job.title,
    ):
        console.print(f"[dim]skip {job.title[:40]} - already applied or reserved[/dim]")
        return _result(job, fingerprint, "failed", "unknown", "duplicate")

    page.goto(job.url, wait_until="domcontentloaded", timeout=config.navigation_timeout_ms)
    page.wait_for_timeout(2000)

    challenge = indeed_form.detect_challenge(page)
    if challenge:
        ledger.mark(fingerprint, "blocked", f"challenge:{challenge}")
        raise ApplyBlockedError(challenge, job.url)

    portal: PortalType = indeed_form.detect_portal(page)
    if portal != "indeed":
        reason = "external_portal_deferred" if portal == "external" else "unknown_portal"
        ledger.mark(fingerprint, "blocked", reason)
        console.print(f"[yellow]{job.title[:40]} - {reason}, skipped[/yellow]")
        return _result(job, fingerprint, "blocked", portal, reason)

    try:
        return _fill_and_submit(
            page,
            job,
            fingerprint,
            profile,
            ledger,
            config,
            console,
            confirm=confirm,
            dry_run=dry_run,
        )
    except ApplyBlockedError as error:
        # A challenge is not a failure of the posting: it stopped the run.
        ledger.mark(fingerprint, "blocked", f"challenge:{error}")
        raise
    except Exception as error:
        ledger.mark(fingerprint, "failed", f"error:{type(error).__name__}")
        raise


def _fill_and_submit(
    page: Any,
    job: Job,
    fingerprint: str,
    profile: Profile,
    ledger: ApplicationLedger,
    config: Config,
    console: Console,
    *,
    confirm: bool,
    dry_run: bool,
) -> ApplyResult:
    """Fill the form, persist the draft, and submit when approved."""
    from . import indeed_form

    portal: PortalType = indeed_form.detect_portal(page)

    button = indeed_form.find_apply_button(page)
    if button is None:
        ledger.mark(fingerprint, "blocked", "no_apply_button")
        return _result(job, fingerprint, "blocked", portal, "no_apply_button")

    if not indeed_form.click_element(button):
        ledger.mark(fingerprint, "failed", "apply_button_not_clickable")
        console.print(f"[yellow]{job.title[:40]} - apply button not clickable[/yellow]")
        return _result(job, fingerprint, "failed", portal, "apply_button_not_clickable")
    page.wait_for_timeout(2500)

    draft: dict[str, Any] = {}
    try:
        draft = indeed_form.fill_indeed_form(page, profile, draft)
    except FieldMissingError as error:
        ledger.mark(fingerprint, "blocked", f"missing:{error.question}")
        console.print(f"[yellow]{job.title[:40]} - missing: {error.question}[/yellow]")
        return _result(job, fingerprint, "blocked", portal, f"missing:{error.question}")

    # The persisted draft names the fields that were filled; the values stay
    # in the 0600 profile and are never duplicated into a second store.
    write_draft(
        drafts_dir(config),
        app_id_for(fingerprint),
        draft_payload(
            {
                "fingerprint": fingerprint,
                "current_url": page.url,
                "jk": job.jk,
                "title": job.title,
                "company": job.company,
                "location": job.location,
            },
            draft,
        ),
    )

    # A challenge can appear while the form is being filled; re-check before
    # anything is submitted so a wall is never pushed through.
    challenge = indeed_form.detect_challenge(page)
    if challenge:
        ledger.mark(fingerprint, "blocked", f"challenge:{challenge}")
        raise ApplyBlockedError(challenge, page.url)

    if dry_run:
        # A rehearsal must not consume the posting: release the reservation so
        # the real run can still apply to it.
        ledger.mark(fingerprint, "failed", "dry_run")
        console.print(f"[cyan]dry-run[/cyan] {job.title[:40]} - filled, not submitted")
        return _result(job, fingerprint, "failed", portal, "dry_run")

    if confirm:
        console.print(f"[bold]Submit application for {job.title} ({job.company})?[/bold]")
        if not console.input("[yellow]type 'yes' to submit: [/yellow]").strip().lower().startswith("y"):
            ledger.mark(fingerprint, "failed", "operator_declined")
            return _result(job, fingerprint, "failed", portal, "operator_declined")

    submitted = indeed_form.submit_application(page)
    if not submitted:
        ledger.mark(fingerprint, "failed", "submit_not_confirmed")
        return _result(job, fingerprint, "failed", portal, "submit_not_confirmed")

    ledger.mark(fingerprint, "submitted", "")
    console.print(f"[green]submitted[/green] {job.title[:40]} ({job.company})")
    return _result(job, fingerprint, "submitted", portal, "")
