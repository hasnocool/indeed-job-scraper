"""The apply-side commands: ``apply``, ``resume``, ``check-responses``, ``profile``.

These live in their own module so ``cli.py`` stays a thin Typer wiring layer.
The command names, flags, help text and output are unchanged - only the
location of the code moved.

The business logic that is worth testing lives here too:
:func:`exit_code_for` and :func:`resolve_policy` are pure functions, so the
safety contract can be pinned without a browser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from ..apply.autonomy import LEVELS, AutonomyPolicy
from ..errors import IndeedScraperError
from .apply import exit_code_for

__all__ = [
    "exit_code_for",
    "register",
    "resolve_policy",
]


def resolve_policy(
    console: Console,
    autonomy: str | None,
    max_per_day: int | None,
    min_delay: float | None,
    policy_path: Path | None = None,
) -> AutonomyPolicy:
    """Resolve the autonomy policy: the policy file, with optional overrides.

    The policy FILE is the operator's standing decision, so it is the
    CEILING. A flag may only LOWER the daily cap or LENGTHEN the minimum
    delay, and may only LOWER the autonomy level. A flag can never raise the
    file's ceiling, and the unattended-submit switch is not reachable through
    a level flag at all - only the operator's own policy file can enable it.

    The previous version overwrote the file's numbers with the flag's, so
    ``--max-per-day 25`` silently raised a file's cap of 2 and
    ``--min-delay 5`` silently removed a file's 30-minute pacing. That is
    exactly the ToS risk budget (HC-5) that the file is meant to hold.
    """
    try:
        rules = AutonomyPolicy.load(policy_path)
    except IndeedScraperError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    level = rules.level
    if autonomy:
        level = autonomy.strip().lower()
        if level not in LEVELS:
            console.print(f"[red]--autonomy must be one of {', '.join(LEVELS)}[/red]")
            raise typer.Exit(code=1)
    requested = level  # type: ignore[assignment]
    if requested != rules.level:
        capped = rules.restrict_to(requested)
        if capped.level != requested:
            console.print(
                f"[yellow]--autonomy {requested} is above the policy file "
                f"({rules.level}); using {capped.level}.[/yellow]"
            )
        rules = capped
    # A flag may only tighten the budget. Tightening the daily cap means a
    # SMALLER number; tightening the pacing means a LONGER delay.
    max_applications_per_day = (
        min(rules.max_applications_per_day, max_per_day)
        if max_per_day is not None
        else rules.max_applications_per_day
    )
    min_delay_minutes = (
        max(rules.min_delay_minutes, min_delay)
        if min_delay is not None
        else rules.min_delay_minutes
    )
    if max_per_day is not None and max_per_day > rules.max_applications_per_day:
        console.print(
            f"[yellow]--max-per-day {max_per_day} is above the policy file "
            f"({rules.max_applications_per_day}); using {max_applications_per_day}.[/yellow]"
        )
    if min_delay is not None and min_delay < rules.min_delay_minutes:
        console.print(
            f"[yellow]--min-delay {min_delay} is below the policy file "
            f"({rules.min_delay_minutes}m); using {min_delay_minutes}m.[/yellow]"
        )
    return AutonomyPolicy(
        level=rules.level,
        max_applications_per_day=max_applications_per_day,
        min_delay_minutes=min_delay_minutes,
        allow_binding_commitments=rules.allow_binding_commitments,
        unattended_submit=rules.unattended_submit,
    )


def register(app: typer.Typer, console: Console, config_factory: Any) -> None:
    """Register the apply-side commands on the Typer app.

    ``config_factory`` is the CLI's ``_config`` helper, injected so the
    commands stay testable without importing the whole CLI.
    """
    # The flow and the profile loader are looked up at CALL time, not at
    # registration time, so a test that patches
    # ``indeed_scraper.apply.flow.apply_to_jobs`` patches the function this
    # command actually runs.
    from ..apply import flow as _flow
    from ..apply import profile as _profile_module
    from ..apply.exceptions import ProfileNotFoundError
    from ..apply.reporting import write_apply_results
    from ..apply.workspace import ledger_path
    from ..cookies import CookieStore

    @app.command()
    def apply(
        limit: int = typer.Option(10, "--limit", "-n", help="Maximum postings to consider."),
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Fill the form and record it, but never submit."
        ),
        profile_path: Path = typer.Option(  # noqa: B008 - typer's option pattern
            None, "--profile", help="Profile file (default ~/.config/indeed_scraper/profile.json)."
        ),
        autonomy: str = typer.Option(
            None,
            "--autonomy",
            help="manual | auto | full. Lowers the policy file's level for this run.",
        ),
        max_per_day: int = typer.Option(
            None, "--max-per-day", help="Lower the daily application cap for this run."
        ),
        min_delay: float = typer.Option(
            None, "--min-delay", help="Raise the minimum delay between submissions (minutes)."
        ),
    ) -> None:
        """Apply to postings from the organized master dataset.

        Every application is reserved in the ledger before the browser is touched,
        so a posting is never applied to twice. Whether a submission is confirmed
        first is decided by the AUTONOMY POLICY
        (~/.config/indeed_scraper/policy.json):

            manual  every submission is confirmed by the operator
            auto    submissions MAY be sent unattended, inside the risk budget
            full    submissions MAY be sent unattended, inside the risk budget

        The policy level is only a PERMISSION. An unattended submit also needs
        the policy file's explicit ``unattended_submit: true`` switch, and no
        command-line flag can turn it on - only the operator's own policy file
        can. A reply that accepts an offer is never sent unattended unless the
        policy explicitly allows binding commitments. A challenge stops the run
        so the shared session is never poisoned.

        The exit code is the machine-readable outcome: 0 when something was
        submitted (or a dry run did what it was asked), 2 when nothing was
        submitted and at least one attempt failed, 3 when a challenge stopped
        the run.
        """
        try:
            profile = _profile_module.load_profile(profile_path)
        except ProfileNotFoundError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=1) from error

        config = config_factory()
        store = CookieStore(config)
        rules = resolve_policy(console, autonomy, max_per_day, min_delay)
        console.print(f"[dim]autonomy: {rules.describe()}[/dim]")
        try:
            results = _flow.apply_to_jobs(
                config,
                store,
                console,
                profile=profile,
                limit=limit,
                confirm=True,
                dry_run=dry_run,
                policy=rules,
            )
        except IndeedScraperError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=1) from error

        if not results:
            console.print("[yellow]Nothing to apply to.[/yellow]")
            return
        out = write_apply_results(results, config.state_dir / "applications" / "applications.csv")
        table = Table(title="Applications")
        table.add_column("Job ID", style="cyan")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Status")
        table.add_column("Detail")
        for result in results:
            table.add_row(result.app_id, result.title[:40], result.company[:24], result.status, result.detail[:28])
        console.print(table)
        console.print(f"[green]results written to {out}[/green]")
        console.print(f"[dim]ledger: {ledger_path(config)}[/dim]")
        raise typer.Exit(code=exit_code_for(results, dry_run=dry_run))

    # The resume / check-responses commands live in their own module so this
    # one stays under the 250-LOC ceiling.
    from .resume_cmds import register_resume_commands

    register_resume_commands(app, console, config_factory, resolve_policy)

    # The profile commands live in their own module for the same reason.
    from .profile import register_profile_commands

    register_profile_commands(app, console)
