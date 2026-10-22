"""Command line interface: login, scrape, status, cookies, doctor, organize."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .auth import ensure_session, login_flow, print_cookie_table, verify_session
from .config import (
    DEFAULT_LOCATIONS,
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_DELAY_S,
    DEFAULT_SITE,
    Config,
    SearchParams,
)
from .cookies import CookieSession, CookieStore
from .errors import IndeedScraperError, SessionExpiredError
from .export import jobs_to_csv, write_json
from .organize import organize_outputs
from .scraper import ScrapeResult, run_scrape

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Indeed scraper with cookie sessions")
console = Console()


_DEFAULT_LOCATION_LIST = list(DEFAULT_LOCATIONS)


def _config(
    *,
    site: str = DEFAULT_SITE,
    headless: bool = False,
    page_delay_s: float | None = None,
    login_timeout_s: int | None = None,
) -> Config:
    config = Config.load(
        site=site,
        headless=headless,
        page_delay_s=page_delay_s,
        login_timeout_s=login_timeout_s,
    )
    config.ensure_dirs()
    return config


def _expiry_text(session: CookieSession) -> str:
    expiry = session.expires_at()
    if expiry is None:
        return "session cookies (until Indeed revokes them)"
    return expiry.strftime("%Y-%m-%d %H:%M UTC")


def _status_table(session: CookieSession | None, site: str) -> Table:
    table = Table(title="Saved Indeed session", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("site", site)
    table.add_row("default locations", ", ".join(DEFAULT_LOCATIONS))
    if session is None:
        table.add_row("state", "[yellow]no session saved[/yellow]")
        return table
    table.add_row("session id", session.id)
    table.add_row("status", session.status)
    table.add_row("source", session.source)
    table.add_row("signed in", "yes" if session.is_signed_in() else "no")
    table.add_row("created", session.created_at.strftime("%Y-%m-%d %H:%M UTC"))
    table.add_row("updated", session.updated_at.strftime("%Y-%m-%d %H:%M UTC"))
    table.add_row("expires", _expiry_text(session))
    table.add_row("cookies saved", str(len(session.cookies)))
    table.add_row("auth cookies", ", ".join(sorted(c.name for c in session.auth_cookies())))
    return table


@app.command()
def login(
    timeout: int = typer.Option(600, "--timeout", "-t", help="Seconds to wait for sign-in."),
    site: str = typer.Option(DEFAULT_SITE, "--site", help="Indeed host to open."),
) -> None:
    """Open a browser and wait for you to sign in to Indeed."""
    config = _config(login_timeout_s=timeout, site=site)
    store = CookieStore(config)
    try:
        session = login_flow(config, store, console)
    except IndeedScraperError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    console.print(
        Panel(
            f"Session [bold]{session.id}[/bold] saved with {len(session.cookies)} cookies.\n"
            f"Cookie list: {config.current_cookie_file}\n"
            f"History: {config.history_file}",
            title="Signed in",
            border_style="green",
        )
    )


@app.command()
def verify() -> None:
    """Confirm Indeed still accepts the saved cookie list."""
    config = _config()
    store = CookieStore(config)
    try:
        verify_session(config, store, console)
    except IndeedScraperError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error


@app.command()
def scrape(
    query: str = typer.Option("", "--query", "-q", help="Keywords; empty lists every job."),
    locations: list[str] = typer.Option(  # noqa: B008 - typer's required option pattern
        _DEFAULT_LOCATION_LIST, "--location", "-l", help="Repeat for several locations."
    ),
    pages: int = typer.Option(
        DEFAULT_MAX_PAGES, "--pages", "-n", help="Maximum result pages per location."
    ),
    site: str = typer.Option(DEFAULT_SITE, "--site", help="Indeed host, e.g. ca.indeed.com."),
    headless: bool = typer.Option(False, "--headless", help="Hide the browser (likely blocked)."),
    delay: float = typer.Option(
        DEFAULT_PAGE_DELAY_S, "--delay", help="Seconds between result pages."
    ),
    csv: bool = typer.Option(True, "--csv/--no-csv", help="Also write a CSV file."),
    relogin: bool = typer.Option(
        True, "--relogin/--no-relogin", help="Sign in again if Indeed rejects the session."
    ),
) -> None:
    """Scrape job listings using the saved Indeed session."""
    config = _config(site=site, headless=headless, page_delay_s=delay)
    store = CookieStore(config)
    params = SearchParams(query=query, locations=tuple(locations), max_pages=pages)

    try:
        session = ensure_session(config, store, console)
    except IndeedScraperError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    console.print(
        f"[cyan]Scope:[/cyan] {'all jobs' if not params.query else params.query} in "
        f"{', '.join(params.locations)} ({params.max_pages} pages each)"
    )

    def attempt(current: CookieSession) -> ScrapeResult:
        return run_scrape(config, params, current, store, console)

    try:
        result = attempt(session)
    except SessionExpiredError as error:
        console.print(f"[yellow]{error}[/yellow]")
        if not relogin or config.headless:
            raise typer.Exit(code=1) from error
        session = login_flow(config, store, console)
        result = attempt(session)

    json_path = write_json(result, config.runs_dir, config.latest_dir)
    csv_path = jobs_to_csv(result.jobs, config.latest_dir / "jobs_latest.csv") if csv else None

    organize_result = organize_outputs(config, console)

    summary = Table(title="Scrape complete")
    summary.add_column("Field", style="cyan")
    summary.add_column("Value")
    summary.add_row("jobs collected", str(len(result.jobs)))
    summary.add_row("pages fetched", str(result.pages))
    for report in result.reports:
        summary.add_row(
            f"  {report.location}",
            f"{report.pages} pages, +{report.found} new ({report.stopped_reason})",
        )
    summary.add_row("session id", result.session.id)
    summary.add_row("session expires", _expiry_text(result.session))
    summary.add_row("json", str(json_path))
    if csv_path is not None:
        summary.add_row("csv", str(csv_path))
    summary.add_row("new postings", str(organize_result["unique_jobs"]))
    summary.add_row("updated postings", str(0))  # no ongoing updates in pure replay
    summary.add_row("unchanged postings", str(0))
    summary.add_row("duplicate postings", str(organize_result["duplicate_postings"]))
    summary.add_row("master unique jobs", str(organize_result["unique_jobs"]))
    summary.add_row("master total postings", str(organize_result["unique_jobs"]))
    console.print(summary)


@app.command()
def status() -> None:
    """Show the saved session, its cookie list and its expiry."""
    config = _config()
    store = CookieStore(config)
    session = store.current()
    console.print(_status_table(session, config.site))
    if session is not None:
        print_cookie_table(session, console)
    history = store.history(limit=8)
    if history:
        events = Table(title="Recent cookie history")
        events.add_column("At")
        events.add_column("Event")
        events.add_column("Session")
        events.add_column("Detail")
        for event in history:
            detail = ", ".join(
                f"{key}={value}"
                for key, value in event.items()
                if key not in {"event", "session_id", "at"}
            )
            events.add_row(
                str(event.get("at", ""))[:19],
                str(event.get("event", "")),
                str(event.get("session_id", "")),
                detail,
            )
        console.print(events)


@app.command()
def cookies(as_json: bool = typer.Option(False, "--json", help="Print the raw cookie list.")) -> None:
    """Print the cookie list currently in use."""
    config = _config()
    session = CookieStore(config).current()
    if session is None:
        console.print("[yellow]No session saved yet.[/yellow]")
        raise typer.Exit(code=1)
    if as_json:
        console.print(json.dumps(session.model_dump(mode="json"), indent=2))
        return
    print_cookie_table(session, console)


@app.command()
def doctor() -> None:
    """Check that this machine can run the scraper end to end."""
    config = _config()
    checks: list[tuple[str, bool, str]] = []
    checks.append(("python", sys.version_info >= (3, 10), sys.version.split()[0]))

    try:
        import playwright

        checks.append(("playwright", True, getattr(playwright, "__version__", "installed")))
    except ImportError:
        checks.append(("playwright", False, "missing — pip install playwright"))

    browsers = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    checks.append(
        ("chromium binary", bool(browsers), str(browsers[-1]) if browsers else "missing")
    )

    store = CookieStore(config)
    session = store.current()
    checks.append(
        (
            "saved session",
            session is not None and session.is_signed_in() and not session.is_expired(),
            session.id if session else "none — run 'login'",
        )
    )
    checks.append(("state dir", config.state_dir.is_dir(), str(config.state_dir)))

    status = "unreachable"
    reachable = False
    try:
        request = urllib.request.Request(
            f"https://{config.site}/robots.txt",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/141 Safari/537.36"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            status = f"HTTP {response.status}"
            reachable = True
    except urllib.error.HTTPError as error:
        status = f"HTTP {error.code} (bot-checked but reachable)"
        reachable = True
    except (urllib.error.URLError, TimeoutError) as error:
        status = f"unreachable: {error}"
    checks.append(("indeed reachable", reachable, status))

    table = Table(title="Environment check")
    table.add_column("Check", style="cyan")
    table.add_column("Result", justify="center")
    table.add_column("Detail")
    for name, ok, detail in checks:
        table.add_row(name, "[green]ok[/green]" if ok else "[red]fail[/red]", detail)
    console.print(table)

    if not all(ok for _, ok, _ in checks):
        raise typer.Exit(code=1)


@app.command()
def organize() -> None:
    """Run the organize flow to refresh data/master from run files.

    No session or browser needed; replays historical runs and prints
    a summary of new/updated/unchanged jobs plus duplicate detection.
    """
    config = _config()
    organize_outputs(config, console)


def _policy(
    autonomy: str | None,
    max_per_day: int | None,
    min_delay: float | None,
    policy_path: Path | None = None,
):
    """Resolve the autonomy policy: the policy file, with optional overrides.

    The policy FILE is the operator's standing decision, so it is the
    CEILING: a flag may only LOWER the daily cap or LENGTHEN the minimum
    delay, and may only LOWER the autonomy level. A flag can never raise the
    file's ceiling, and the unattended-submit switch is not reachable through
    a level flag at all.
    """
    from .commands.apply_cmds import resolve_policy

    return resolve_policy(console, autonomy, max_per_day, min_delay, policy_path)


def _mirror_tracker_statuses(ledger, entries, state_dir) -> int:
    """Copy Indeed's status for our applications into a SEPARATE store.

    Two rules make this safe:

    * The tracker status is never written into the application ledger. The
      ledger's status is the IDEMPOTENCY GUARD ("submitted" means submitted);
      overwriting it with "hired" or "offer" would let the flow apply to the
      same posting a second time.
    * A tracker row is matched to a ledger entry only when the title AND the
      company match, and only when that match is UNIQUE. An ambiguous match
      is skipped rather than guessed, because writing to the wrong application
      is worse than not writing at all.
    """
    from .apply.tracker import record_tracker_status

    mirrored = 0
    for entry in entries:
        if not entry.title or entry.status == "unknown":
            continue
        candidates = [
            record
            for record in ledger.entries
            if _tracker_row_matches(record, entry)
        ]
        if len(candidates) != 1:
            # Zero matches: we did not apply to it. More than one: ambiguous.
            continue
        fingerprint = str(candidates[0].get("fingerprint", ""))
        if not fingerprint:
            continue
        record_tracker_status(
            state_dir,
            fingerprint=fingerprint,
            status=entry.status,
            status_text=entry.status_text,
            title=entry.title,
            company=entry.company,
        )
        mirrored += 1
    return mirrored


def _tracker_row_matches(record: dict, entry) -> bool:
    """True when a ledger row is the SAME posting as a tracker row."""
    title = str(record.get("title", "")).strip().lower()
    company = str(record.get("company", "")).strip().lower()
    if not title or not company:
        return False
    return (
        title == entry.title.strip().lower()
        and company == entry.company.strip().lower()
    )


resume_app = typer.Typer(help="Convert a resume between formats.")
app.add_typer(resume_app, name="resume-doc")


@resume_app.command("convert")
def resume_doc_convert(
    source: Path = typer.Argument(  # noqa: B008 - typer's argument pattern
        ..., help="The resume file to read."
    ),
    target: Path = typer.Argument(  # noqa: B008 - typer's argument pattern
        ..., help="The file to write; its extension picks the format."
    ),
) -> None:
    """Convert a resume between DOCX, Markdown, text, JSON, YAML and TOML."""
    from .resume import ResumeError, convert_file

    try:
        written = convert_file(source, target)
    except ResumeError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    console.print(f"[green]wrote {written}[/green]")


@resume_app.command("formats")
def resume_doc_formats() -> None:
    """Show the resume formats this tool can read and write."""
    from .resume import DEFAULT_EXTENSIONS

    table = Table(title="Resume formats")
    table.add_column("Format")
    table.add_column("Extension")
    for name, extension in DEFAULT_EXTENSIONS.items():
        table.add_row(str(name), extension)
    console.print(table)


def _register_apply_commands() -> None:
    """Wire the apply-side commands onto the Typer app.

    Their bodies live in :mod:`indeed_scraper.commands.apply_cmds` so this
    module stays a thin wiring layer.

    The config factory is passed as a LAZY LOOKUP, not as the function
    object. The commands are registered at import time, so passing
    ``_config`` itself froze the ORIGINAL function into their closures: a
    test's ``monkeypatch.setattr(cli, "_config", ...)`` replaced the
    module attribute, but the already-registered command kept calling the
    function it had captured - so it used the real config and wrote into
    the operator's real ``data/`` directory.

    Resolving ``cli._config`` at CALL time makes the patch reach the
    command that is actually registered.
    """
    from .commands.apply_cmds import register

    def _late_bound_config(**kwargs):
        """The CLI's current ``_config``, resolved when the command runs."""
        return _config(**kwargs)

    register(app, console, _late_bound_config)


_register_apply_commands()


@app.command()
def sync() -> None:
    """Read Indeed's application tracker and mirror the status locally.

    Indeed records the outcome of every application (Applied, Interviewing,
    Offer received, Hired, ...). This reads that status and records it in the
    tracker store, so an offer that Indeed has recorded is surfaced to the
    operator instead of being acted on.

    The status is deliberately NOT written into the application ledger: the
    ledger's status is the idempotency guard, and overwriting "submitted"
    with "hired" would let the flow apply to the same posting again.
    """
    from .apply.driver import open_driver
    from .apply.ledger import ApplicationLedger
    from .apply.tracker import (
        action_required,
        open_tracker,
        read_tracker,
    )
    from .apply.workspace import ledger_path

    config = _config()
    store = CookieStore(config)
    session = store.current()
    if session is None or not session.is_signed_in():
        console.print("[red]No signed-in Indeed session. Run 'login' first.[/red]")
        raise typer.Exit(code=1)
    with open_driver(config, session) as (context, _info):
        open_tracker(context.pages[0] if context.pages else context.new_page())
        entries = read_tracker(context.pages[0] if context.pages else context.new_page())
    ledger = ApplicationLedger(ledger_path(config))
    mirrored = _mirror_tracker_statuses(ledger, entries, config.state_dir)
    table = Table(title="Indeed application tracker")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Status")
    table.add_column("Applied")
    escalated = 0
    for entry in entries:
        if action_required(entry):
            escalated += 1
        table.add_row(
            entry.title[:40] or "-",
            entry.company[:22] or "-",
            entry.status,
            entry.applied_on[:26] or "-",
        )
    console.print(table)
    console.print(f"[dim]{len(entries)} applications on Indeed[/dim]")
    if mirrored:
        console.print(
            f"[green]mirrored {mirrored} status change(s) into the tracker store[/green]"
        )
    if escalated:
        console.print(
            f"[yellow]{escalated} application(s) need your attention (offer or hired). "
            "They are never acted on automatically.[/yellow]"
        )


@app.command()
def messages(
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum conversations to consider."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Draft the replies but send nothing."
    ),
    autonomy: str = typer.Option(
        None,
        "--autonomy",
        help="manual | auto | full. Lowers the policy file's level for this run; never raises it.",
    ),
    profile_path: Path = typer.Option(  # noqa: B008 - typer's option pattern
        None, "--profile", help="Profile file (default ~/.config/indeed_scraper/profile.json)."
    ),
) -> None:
    """Read the Indeed inbox and answer the recruiters.

    Replies are built from the operator profile. Whether they are sent or only
    drafted depends on the autonomy policy; a reply that accepts an offer is
    never sent without the operator's explicit approval.
    """
    from .apply.exceptions import ProfileNotFoundError
    from .apply.profile import load_profile
    from .messages.flow import handle_inbox, print_outcomes

    try:
        profile = load_profile(profile_path)
    except ProfileNotFoundError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    config = _config()
    store = CookieStore(config)
    rules = _policy(autonomy, None, None)
    console.print(f"[dim]autonomy: {rules.describe()}[/dim]")
    try:
        outcomes = handle_inbox(
            config,
            store,
            console,
            profile=profile,
            policy=rules,
            limit=limit,
            dry_run=dry_run,
        )
    except IndeedScraperError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    if outcomes:
        print_outcomes(outcomes, console)
    else:
        console.print("[yellow]No conversations to handle.[/yellow]")
    from .messages.store import sent_ledger_path

    console.print(f"[dim]message log: {sent_ledger_path(config.state_dir)}[/dim]")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by python -m and the legacy script."""
    try:
        app(args=list(argv) if argv is not None else None)
    except KeyboardInterrupt:
        return 130
    return 0
