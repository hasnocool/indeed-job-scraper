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
        help="manual | auto | full. Overrides the policy file for this run.",
    ),
    max_per_day: int = typer.Option(
        None, "--max-per-day", help="Override the daily application cap for this run."
    ),
    min_delay: float = typer.Option(
        None, "--min-delay", help="Override the minimum delay between submissions (minutes)."
    ),
) -> None:
    """Apply to postings from the organized master dataset.

    Every application is reserved in the ledger before the browser is touched,
    and a submission ALWAYS requires the operator to confirm it - there is no
    flag that skips that gate. A challenge stops the run so the shared session is
    never poisoned.
    """
    from .apply.exceptions import ProfileNotFoundError
    from .apply.flow import apply_to_jobs
    from .apply.profile import load_profile
    from .apply.reporting import write_apply_results
    from .apply.workspace import ledger_path

    try:
        profile = load_profile(profile_path)
    except ProfileNotFoundError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    config = _config()
    store = CookieStore(config)
    rules = _policy(autonomy, max_per_day, min_delay)
    console.print(f"[dim]autonomy: {rules.describe()}[/dim]")
    try:
        results = apply_to_jobs(
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


@app.command("resume")
def resume(
    app_id: str = typer.Argument(..., help="Application id (the 12-char job id)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Refill but do not submit."),
    autonomy: str = typer.Option(
        None, "--autonomy", help="manual | auto | full. Overrides the policy file for this run."
    ),
) -> None:
    """Resume an interrupted application from its persisted draft."""
    from .apply.exceptions import ProfileNotFoundError
    from .apply.flow import resume_application
    from .apply.profile import load_profile

    try:
        profile = load_profile()
    except ProfileNotFoundError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    config = _config()
    store = CookieStore(config)
    rules = _policy(autonomy, None, None)
    console.print(f"[dim]autonomy: {rules.describe()}[/dim]")
    try:
        result = resume_application(
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
    """
    from .apply.workspace import ledger_path, responses_dir
    from .response_monitor.indeed import collect_responses

    config = _config()
    records = collect_responses(ledger_path(config), responses_dir(config))
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


def _policy(autonomy: str | None, max_per_day: int | None, min_delay: float | None):
    """Resolve the autonomy policy: the policy file, with optional overrides."""
    from .apply.autonomy import LEVELS, AutonomyPolicy

    try:
        rules = AutonomyPolicy.load()
    except IndeedScraperError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    level = rules.level
    if autonomy:
        level = autonomy.strip().lower()
        if level not in LEVELS:
            console.print(f"[red]--autonomy must be one of {', '.join(LEVELS)}[/red]")
            raise typer.Exit(code=1)
    rules = AutonomyPolicy(
        level=level,  # type: ignore[arg-type]
        max_applications_per_day=rules.max_applications_per_day if max_per_day is None else max_per_day,
        min_delay_minutes=rules.min_delay_minutes if min_delay is None else min_delay,
        allow_binding_commitments=rules.allow_binding_commitments,
    )
    return rules


def _mirror_tracker_statuses(ledger, entries) -> int:
    """Copy Indeed's status for our applications into the local ledger.

    Matched on title and company: the ledger does not know Indeed's internal
    application id, but both sides carry the posting identity.
    """
    mirrored = 0
    for entry in entries:
        if not entry.title or entry.status == "unknown":
            continue
        for record in ledger.entries:
            same_title = str(record.get("title", "")).strip().lower() == entry.title.strip().lower()
            same_company = (
                not record.get("company")
                or not entry.company
                or str(record.get("company")).strip().lower() == entry.company.strip().lower()
            )
            if not (same_title and same_company):
                continue
            fingerprint = str(record.get("fingerprint", ""))
            if not fingerprint:
                continue
            current = ledger.status_of(fingerprint)
            if current != entry.status:
                ledger.mark(fingerprint, entry.status, f"indeed:{entry.status_text or entry.status}")
                mirrored += 1
            break
    return mirrored


profile_app = typer.Typer(help="Inspect and fix the operator profile.")
app.add_typer(profile_app, name="profile")


@profile_app.command("init")
def profile_init(force: bool = typer.Option(False, "--force", help="Overwrite an existing profile.")) -> None:
    """Write a profile template with the right permissions."""
    from .apply.profile import PROFILE_PATH, profile_template, save_profile

    if PROFILE_PATH.exists() and not force:
        console.print(f"[yellow]{PROFILE_PATH} already exists - use --force to overwrite.[/yellow]")
        raise typer.Exit(code=1)
    path = save_profile(profile_template(), PROFILE_PATH)
    console.print(f"[green]wrote {path} (0600)[/green]")
    console.print(
        "[yellow]Next: put your resume PDF at the resume_path in that file, then run "
        "'profile set-resume <path>'.[/yellow]"
    )


@profile_app.command("show")
def profile_show() -> None:
    """Show the current profile and whether the resume is usable."""
    import json

    from .apply.profile import PROFILE_PATH, validate_resume

    if not PROFILE_PATH.exists():
        console.print(f"[yellow]No profile at {PROFILE_PATH} - run 'profile init'.[/yellow]")
        raise typer.Exit(code=1)
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    table = Table(title=f"Profile {PROFILE_PATH}")
    table.add_column("Field")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(key, str(value)[:60])
    console.print(table)
    try:
        validate_resume(Path(str(data.get("resume_path", ""))).expanduser())
        console.print("[green]resume: ready[/green]")
    except Exception as error:  # noqa: BLE001 - reported, not raised
        console.print(f"[red]resume: {error}[/red]")


@profile_app.command("set-resume")
def profile_set_resume(
    resume: Path = typer.Argument(  # noqa: B008 - typer's required argument pattern
        ..., help="Path to your resume PDF."
    ),
) -> None:
    """Point the profile at your resume PDF (validated before it is saved)."""
    import json

    from .apply.profile import PROFILE_PATH, validate_resume

    if not PROFILE_PATH.exists():
        console.print(f"[yellow]No profile at {PROFILE_PATH} - run 'profile init' first.[/yellow]")
        raise typer.Exit(code=1)
    try:
        validate_resume(resume.expanduser())
    except Exception as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    data["resume_path"] = str(resume.expanduser())
    path = PROFILE_PATH
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    console.print(f"[green]resume_path set to {data['resume_path']}[/green]")


@app.command()
def sync() -> None:
    """Read Indeed's application tracker and mirror the status locally.

    Indeed records the outcome of every application (Applied, Interviewing,
    Offer received, Hired, ...). This reads that status and writes it into the
    application ledger, so an offer that Indeed has recorded is surfaced to the
    operator instead of being acted on.
    """
    from .apply.driver import open_driver
    from .apply.ledger import ApplicationLedger
    from .apply.tracker import action_required, open_tracker, read_tracker
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
    mirrored = _mirror_tracker_statuses(ledger, entries)
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
        console.print(f"[green]mirrored {mirrored} status change(s) into the ledger[/green]")
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
        None, "--autonomy", help="manual | auto | full. Overrides the policy file for this run."
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
