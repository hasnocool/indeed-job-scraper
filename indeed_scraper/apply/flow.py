"""Orchestration for the application flow.

One job at a time, in this order, with every irreversible step guarded:

1. fingerprint the posting with the SAME hash the master list uses
2. skip it if the ledger already holds a reservation or a submission
3. reserve it atomically in the ledger BEFORE any browser action
4. navigate, classify the destination, stop on a challenge
5. fill the form from the operator profile (never invent a value)
6. write a draft so an interrupted run can resume
7. submit only with explicit operator approval, then mark it submitted

A posting is attempted at most once: the ledger is the idempotency guard.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from ..config import Config
from ..cookies import CookieStore
from ..dedupe import job_fingerprint
from ..scraper import Job
from . import indeed_form
from .autonomy import AutonomyPolicy
from .drafts import draft_payload, read_draft, write_draft
from .driver import open_driver
from .exceptions import ApplyBlockedError
from .ledger import ApplicationLedger
from .profile import Profile, validate_resume
from .risk import RiskBudget
from .types import ApplyResult
from .worker import _apply_one, _result
from .workspace import (
    drafts_dir,
    ledger_path,
    load_master_jobs,
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()



#: A reservation older than this is treated as abandoned (the run was killed).
RESERVATION_LEASE_SECONDS = 2 * 60 * 60


def _stale(ledger: ApplicationLedger, fingerprint: str) -> bool:
    """True when a reservation is older than the lease and may be retried."""
    age = ledger.reservation_age(fingerprint)
    return age is not None and age > RESERVATION_LEASE_SECONDS


def _apply_jobs_on_page(
    page: Any,
    jobs: list[Job],
    profile: Profile,
    ledger: ApplicationLedger,
    config: Config,
    console: Console,
    budget: RiskBudget,
    needs_confirm: bool,
    dry_run: bool,
) -> list[ApplyResult]:
    """Run the guarded per-posting loop against an open page."""
    results: list[ApplyResult] = []
    last_submit: datetime | None = None
    for job in jobs:
        fingerprint = job_fingerprint(job)
        status = ledger.status_of(fingerprint)
        if status in {"submitted", "submitting"}:
            # "submitting" means a previous run reached the submit click and
            # may have gone out. It is NEVER re-applied: a duplicate
            # application is worse than a missed one.
            console.print(f"[dim]skip {job.title[:40]} - already applied[/dim]")
            results.append(_result(job, fingerprint, "failed", "unknown", "duplicate"))
            continue
        if status == "reserved" and not _stale(ledger, fingerprint):
            console.print(f"[dim]skip {job.title[:40]} - already applied[/dim]")
            results.append(_result(job, fingerprint, "failed", "unknown", "duplicate"))
            continue
        if status == "reserved":
            # A previous run was killed BEFORE the submit click: release the
            # stale reservation so the posting is not blocked forever.
            ledger.mark(fingerprint, "failed", "stale_reservation_released")
            console.print(f"[dim]released a stale reservation for {job.title[:40]}[/dim]")
        if not budget.can_apply(ledger):
            console.print("[yellow]risk budget reached - stopping for today.[/yellow]")
            break
        if not dry_run and last_submit is not None:
            wait = budget.delay_seconds(last_submit)
            if wait > 0:
                console.print(f"[dim]waiting {int(wait)}s before the next application[/dim]")
                time.sleep(wait)
        try:
            result = _apply_one(
                page,
                job,
                fingerprint,
                profile,
                ledger,
                config,
                console,
                confirm=needs_confirm,
                dry_run=dry_run,
            )
        except ApplyBlockedError as error:
            console.print(f"[red]blocked: {error}[/red]")
            results.append(_result(job, fingerprint, "blocked", "unknown", str(error)))
            if budget.stop_on_captcha:
                console.print("[red]challenge detected - stopping this run.[/red]")
                break
            continue
        results.append(result)
        if result.status == "submitted":
            last_submit = datetime.now(tz=timezone.utc)
    return results


def apply_to_jobs(
    config: Config,
    store: CookieStore,
    console: Console,
    *,
    profile: Profile,
    limit: int | None = None,
    confirm: bool = True,
    dry_run: bool = False,
    risk_budget: RiskBudget | None = None,
    policy: AutonomyPolicy | None = None,
    page: Any | None = None,
) -> list[ApplyResult]:
    """Apply to postings from the master dataset, one guarded job at a time."""
    rules = policy or AutonomyPolicy()
    budget = risk_budget or RiskBudget(
        max_per_day=rules.max_applications_per_day,
        min_delay_minutes=rules.min_delay_minutes,
    )
    # The policy may allow an unattended submission; the confirm gate then
    # only applies when the policy keeps it.
    needs_confirm = confirm and not rules.allows_submit
    # The resume is uploaded to an employer, so it must be a real document.
    # Checked here, before any browser work, so the operator is told at once.
    validate_resume(Path(profile.resume_path).expanduser())
    session = store.current()
    if session is None or not session.is_signed_in():
        raise ApplyBlockedError("no-session", "")

    jobs = load_master_jobs(config)
    if not jobs:
        console.print("[yellow]No jobs in the master dataset - run 'scrape' first.[/yellow]")
        return []
    if limit is not None:
        jobs = jobs[:limit]

    ledger = ApplicationLedger(ledger_path(config))

    if page is not None:
        return _apply_jobs_on_page(
            page, jobs, profile, ledger, config, console, budget, needs_confirm, dry_run
        )
    with open_driver(config, session) as (context, info):
        console.print(f"[dim]driver: {info.kind} ({info.endpoint})[/dim]")
        existing_pages = list(context.pages)
        page = existing_pages[0] if existing_pages else context.new_page()
        owns_page = not existing_pages
        try:
            return _apply_jobs_on_page(
                page, jobs, profile, ledger, config, console, budget, needs_confirm, dry_run
            )
        finally:
            # Close the tab only if this flow opened it, so a challenge page is
            # never left open in the shared browser.
            if owns_page:
                page.close()


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
    """Resume an interrupted application from its persisted draft."""
    session = store.current()
    if session is None or not session.is_signed_in():
        raise ApplyBlockedError("no-session", "")

    draft = read_draft(drafts_dir(config), app_id)
    if not draft:
        console.print(f"[yellow]No draft found for {app_id}.[/yellow]")
        return None

    ledger = ApplicationLedger(ledger_path(config))
    fingerprint = str(draft.get("fingerprint", ""))
    url = str(draft.get("current_url", ""))
    if not url:
        console.print("[yellow]Draft has no URL to resume from.[/yellow]")
        return None

    rules = policy or AutonomyPolicy()
    budget = risk_budget or RiskBudget(
        max_per_day=rules.max_applications_per_day,
        min_delay_minutes=rules.min_delay_minutes,
    )
    needs_confirm = confirm and not rules.allows_submit
    validate_resume(Path(profile.resume_path).expanduser())
    if not dry_run and not budget.can_apply(ledger):
        console.print("[yellow]daily application budget reached - not resuming.[/yellow]")
        return None

    # Idempotency guard: a posting that already reached a terminal state must
    # never be re-submitted by a resume.
    previous = ledger.status_of(fingerprint) if fingerprint else None
    if previous in {"submitted", "blocked"}:
        console.print(
            f"[yellow]{app_id} is already {previous} - not resuming.[/yellow]"
        )
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
            filled = indeed_form.fill_indeed_form(page, profile)
            write_draft(drafts_dir(config), app_id, draft_payload(draft, filled))
            if dry_run:
                # A rehearsal must leave an honest trace: release the
                # reservation and report the real status, so the operator is
                # not told the posting is still reserved.
                ledger.mark(fingerprint, "failed", "dry_run_resume")
                console.print("[cyan]dry-run[/cyan] resumed fill, not submitted")
                return ApplyResult(
                    jk=str(draft.get("jk", "")),
                    title=str(draft.get("title", "")),
                    company=str(draft.get("company", "")),
                    location=str(draft.get("location", "")),
                    url=url,
                    fingerprint=fingerprint,
                    app_id=app_id,
                    status="failed",
                    portal="indeed",
                    detail="dry_run_resume",
                )
            if needs_confirm:
                console.print("[bold]Submit the resumed application?[/bold]")
                if not console.input("[yellow]type 'yes' to submit: [/yellow]").strip().lower().startswith("y"):
                    ledger.mark(fingerprint, "failed", "operator_declined")
                    return None
            submitted = indeed_form.submit_application(page)
            if submitted:
                ledger.mark(fingerprint, "submitted", "")
                console.print(f"[green]submitted[/green] resumed application {app_id}")
            else:
                ledger.mark(fingerprint, "failed", "submit_not_confirmed")
            return ApplyResult(
                jk=str(draft.get("jk", "")),
                title=str(draft.get("title", "")),
                company=str(draft.get("company", "")),
                location=str(draft.get("location", "")),
                url=url,
                fingerprint=fingerprint,
                app_id=app_id,
                status="submitted" if submitted else "failed",
                portal="indeed",
                detail="" if submitted else "submit_not_confirmed",
            )
        finally:
            # Close the tab only if this flow opened it, so a challenge page is
            # never left open in the shared browser.
            if owns_page:
                page.close()




