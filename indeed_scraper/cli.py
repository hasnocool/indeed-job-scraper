"""Command line interface: login, scrape, status, cookies, doctor."""

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

    json_path = write_json(result, config.output_dir)
    csv_path = jobs_to_csv(result.jobs, config.output_dir / "jobs_latest.csv") if csv else None

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


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by python -m and the legacy script."""
    try:
        app(args=list(argv) if argv is not None else None)
    except KeyboardInterrupt:
        return 130
    return 0
