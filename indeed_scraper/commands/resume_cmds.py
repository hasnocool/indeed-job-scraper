"""The ``resume`` and ``check-responses`` commands.

``resume`` refills an interrupted application from its persisted draft, and
``check-responses`` refreshes the status of every submitted application.

They live in their own module so ``commands/apply_cmds.py`` stays under the
repo's 250-LOC ceiling.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.table import Table

__all__ = ["register_resume_commands"]


def register_resume_commands(
    app: typer.Typer,
    console: Console,
    config_factory: Any,
    resolve_policy: Any,
) -> None:
    """Register the ``resume`` and ``check-responses`` commands on the app.

    ``resolve_policy`` is injected so both command groups resolve the
    autonomy policy through exactly the same code path.
    """

    from ..apply import flow as _flow
    from ..apply import profile as _profile_module
    from ..apply.exceptions import ProfileNotFoundError
    from ..apply.workspace import ledger_path, responses_dir
    from ..cookies import CookieStore
    from ..errors import IndeedScraperError
    from ..response_monitor.indeed import collect_responses

    @app.command("resume")
    def resume(
        app_id: str = typer.Argument(..., help="Application id (the 12-char job id)."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Refill but do not submit."),
        autonomy: str = typer.Option(
            None, "--autonomy", help="manual | auto | full. Lowers the policy file's level for this run."
        ),
    ) -> None:
        """Resume an interrupted application from its persisted draft."""
        try:
            profile = _profile_module.load_profile()
        except ProfileNotFoundError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=1) from error

        config = config_factory()
        store = CookieStore(config)
        rules = resolve_policy(console, autonomy, None, None)
        console.print(f"[dim]autonomy: {rules.describe()}[/dim]")
        try:
            result = _flow.resume_application(
                config,
                store,
                console,
                app_id,
                profile=profile,
                confirm=True,
                dry_run=dry_run,
                policy=rules,
            )
        except IndeedScraperError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=1) from error
        if result is None:
            raise typer.Exit(code=1)
        console.print(f"[green]{app_id}: {result.status}[/green]")

    @app.command("check-responses")
    def check_responses() -> None:
        """Refresh the response status of every submitted application.

        Reads the application ledger and records the current status for each
        submission. No polling, no scheduler: this is a manual command.

        The command opens Indeed's application tracker and reads the REAL
        status of each application. It used to call the monitor with no
        status fetcher at all, so every record came out as "unknown" and
        the command reported the status of nothing.
        """
        config = config_factory()
        records = collect_responses(
            ledger_path(config),
            responses_dir(config),
            fetch_status=_status_fetcher(config, console),
        )
        if not records:
            console.print("[yellow]No submitted applications to check.[/yellow]")
            return
        table = Table(title="Application responses")
        table.add_column("Job ID", style="cyan")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Checked")
        for record in records:
            table.add_row(
                str(record.get("app_id", "")),
                str(record.get("title", ""))[:40],
                str(record.get("status", "")),
                str(record.get("checked_at", ""))[:19],
            )
        console.print(table)


def _status_fetcher(config: Any, console: Console) -> Any:
    """A callable that reads Indeed's live status for a job.

    The tracker is opened ONCE, and the rows are read once; the returned
    callable answers from those rows. Re-reading the tracker for every
    application would be slow and a good way to get rate-limited.

    When the browser cannot be opened - no session, no driver, a challenge
    - the fetcher answers "" instead of raising. The command then reports
    the applications it knows about with an unknown live status, which is
    strictly better than the command refusing to run at all.
    """
    from ..apply.tracker import open_tracker, status_fetcher_for
    from ..cookies import CookieStore

    store = CookieStore(config)
    session = store.current()
    if session is None or not session.is_signed_in():
        console.print(
            "[yellow]No signed-in Indeed session - reporting the ledger statuses only.[/yellow]"
        )
        return lambda jk: ""

    try:
        page = _open_tracker_page(config, session)
        open_tracker(page)
        return status_fetcher_for(page)
    except Exception as error:  # noqa: BLE001 - the tracker is optional
        console.print(f"[yellow]Could not read the tracker: {error}[/yellow]")
        return lambda jk: ""


def _open_tracker_page(config: Any, session: Any) -> Any:
    """Open a browser tab on the application tracker.

    Kept as its own function so a test can supply a page without a
    browser. The driver opens the tab and the CALLER closes it.
    """
    from ..apply.driver import open_driver

    context_manager = open_driver(config, session)
    context, _info = context_manager.__enter__()
    return context.pages[0] if context.pages else context.new_page()
