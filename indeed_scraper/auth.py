"""Human-in-the-loop Indeed sign-in and session capture."""

from __future__ import annotations

import time
from collections.abc import Mapping

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .browser import (
    INDEED_LOGIN,
    INDEED_MY_JOBS,
    active_page,
    challenge_kind,
    challenge_label,
    goto,
    home_url,
    open_context,
    wait_for_challenge,
)
from .config import Config
from .cookies import (
    SESSION_COOKIE_NAMES,
    CookieSession,
    CookieStore,
    SaveSource,
    is_indeed_domain,
)
from .errors import ChallengeBlockedError, LoginTimeoutError, SessionMissingError


def _session_cookie_names(cookies: tuple[object, ...]) -> set[str]:
    """Names of Indeed-domain cookies in a Playwright cookie dump.

    Playwright returns plain dicts, so both mappings and objects are accepted.
    """
    names: set[str] = set()
    for cookie in cookies:
        if isinstance(cookie, Mapping):
            name = cookie.get("name")
            domain = cookie.get("domain", "")
        else:
            name = getattr(cookie, "name", None)
            domain = getattr(cookie, "domain", "")
        if isinstance(name, str) and isinstance(domain, str) and is_indeed_domain(domain):
            names.add(name)
    return names


def has_sign_in_cookie(context: object) -> bool:
    """True when the browser holds a cookie that proves a signed-in session.

    Indeed stopped issuing the legacy "SESS" cookie; current sessions are
    carried by the Passport bearer token, so both families are accepted.
    """
    cookies = getattr(context, "cookies", None)
    if not callable(cookies):
        return False
    return bool(_session_cookie_names(tuple(cookies())) & SESSION_COOKIE_NAMES)


def sign_in_hint(console: Console, config: Config) -> None:
    console.print(
        Panel(
            "A Chromium window is open.\n\n"
            "1. Sign in to Indeed there (email/password, Google or Apple).\n"
            "2. Complete any 2FA or Cloudflare check in that window.\n"
            f"3. Leave the window alone afterwards; it closes by itself within "
            f"{config.login_timeout_s // 60} minutes.\n\n"
            "The session cookie is captured automatically the moment sign-in succeeds.",
            title="Sign in to Indeed",
            border_style="yellow",
        )
    )


def wait_for_sign_in(context: object, page: object, console: Console, config: Config) -> bool:
    """Poll until Indeed issues the SESS cookie (which only happens after login)."""
    deadline = time.monotonic() + config.login_timeout_s
    last_note = 0.0
    while time.monotonic() < deadline:
        if has_sign_in_cookie(context):
            page.wait_for_timeout(1500)  # let the redirect finish
            return True
        remaining = int(deadline - time.monotonic())
        if time.monotonic() - last_note >= 20:
            last_note = time.monotonic()
            console.print(
                f"[dim]waiting for sign-in…[/dim] [bold]{remaining}s[/bold] remaining"
            )
        if page.is_closed():
            break
        page.wait_for_timeout(2000)
    return False


def capture_session(
    store: CookieStore,
    context: object,
    page: object,
    *,
    source: SaveSource,
    notes: tuple[str, ...] = (),
) -> CookieSession:
    from contextlib import suppress

    from .cookies import cookies_from_playwright

    cookies = cookies_from_playwright(context.cookies())
    user_agent = ""
    with suppress(Exception):
        user_agent = str(page.evaluate("navigator.userAgent"))
    current = store.current()
    if current is not None and current.is_signed_in() and current.status == "active":
        return store.refresh(current, cookies=cookies, notes=notes)
    # A fresh sign-in after expiry is a new session, not a refresh of the dead one.

    return store.save(cookies=cookies, source=source, user_agent=user_agent, notes=notes)


def print_cookie_table(session: CookieSession, console: Console) -> None:
    table = Table(title=f"Saved session {session.id}", show_lines=False)
    table.add_column("Cookie", style="cyan")
    table.add_column("Domain")
    table.add_column("Expires", justify="right")
    table.add_column("Flags")
    for cookie in sorted(session.auth_cookies(), key=lambda c: c.name):
        expiry = cookie.expires_at
        table.add_row(
            cookie.name,
            cookie.domain,
            expiry.strftime("%Y-%m-%d %H:%M UTC") if expiry else "session",
            ("httpOnly " if cookie.http_only else "") + ("secure" if cookie.secure else ""),
        )
    console.print(table)
    expires_at = session.expires_at()
    if expires_at is None:
        console.print(
            "[yellow]Auth cookies are browser-session cookies: valid until Indeed revokes them.[/yellow]"
        )
    else:
        left = session.seconds_left()
        console.print(
            f"[green]Session usable until {expires_at:%Y-%m-%d %H:%M UTC} "
            f"({int(left or 0) // 3600}h left).[/green]"
        )


def login_flow(config: Config, store: CookieStore, console: Console) -> CookieSession:
    """Open a visible browser, wait for a human sign-in, persist the cookie list."""
    with open_context(config, headless=False) as context:
        page = active_page(context)
        goto(page, home_url(config.site), config)
        page.wait_for_timeout(1500)

        kind = challenge_kind(page)
        if kind not in {"none", "auth"}:
            console.print(f"[yellow]{challenge_label(kind)} — waiting for you to clear it…[/yellow]")
            kind = wait_for_challenge(page, timeout_s=config.challenge_timeout_s)
            if kind not in {"none", "auth"}:
                raise ChallengeBlockedError(
                    f"Could not clear {challenge_label(kind)} on the Indeed home page."
                )

        if has_sign_in_cookie(context):
            console.print("[green]Existing Indeed session found in the browser profile.[/green]")
            session = capture_session(store, context, page, source="refresh")
            print_cookie_table(session, console)
            return session

        sign_in_hint(console, config)
        goto(page, INDEED_LOGIN, config)
        page.wait_for_timeout(1500)

        kind = challenge_kind(page)
        if kind not in {"none", "auth"}:
            console.print(f"[yellow]{challenge_label(kind)} — waiting for you to clear it…[/yellow]")
            kind = wait_for_challenge(page, timeout_s=config.challenge_timeout_s)
            if kind not in {"none", "auth"}:
                raise ChallengeBlockedError(
                    f"Could not clear {challenge_label(kind)} on the Indeed sign-in page."
                )

        if not wait_for_sign_in(context, page, console, config):
            raise LoginTimeoutError(
                f"No sign-in detected within {config.login_timeout_s}s; nothing was saved."
            )

        session = capture_session(store, context, page, source="login")
        # A saved cookie list is only useful if Indeed accepts it; myjobs is
        # gated behind sign-in, so a redirect back to auth is unambiguous.
        goto(page, INDEED_MY_JOBS, config)
        page.wait_for_timeout(2000)
        if "secure.indeed.com/auth" in page.url:
            console.print(
                "[yellow]Cookies were saved, but Indeed still shows the sign-in wall "
                "for this browser profile.[/yellow]"
            )
        else:
            console.print("[green]Verified: Indeed accepts the new session.[/green]")
            session = capture_session(store, context, page, source="refresh")
        print_cookie_table(session, console)
        return session


def ensure_session(
    config: Config,
    store: CookieStore,
    console: Console,
    *,
    allow_login: bool = True,
) -> CookieSession:
    """Return a usable saved session, signing in when none is valid."""
    session = store.current()
    if session is not None and session.is_signed_in() and not session.is_expired():
        return session
    if session is not None and session.is_signed_in():
        store.mark(session, "expired", reason="cookie expiry reached before use")
    if not allow_login:
        raise SessionMissingError(
            "No valid Indeed session. Run 'python -m indeed_scraper login' first."
        )
    if config.headless:
        raise SessionMissingError(
            "A valid session is required and sign-in needs a visible browser; "
            "drop --headless or run 'python -m indeed_scraper login'."
        )
    console.print("[yellow]No valid saved session — starting interactive sign-in.[/yellow]")
    return login_flow(config, store, console)


def verify_session(config: Config, store: CookieStore, console: Console) -> CookieSession:
    """Open the browser and confirm Indeed still accepts the saved cookies."""
    session = store.require_current()
    if not session.is_signed_in():
        store.mark(session, "expired", reason="session cookie missing")
        raise SessionMissingError(
            "Saved cookie list has no session cookie (SESS or Passport token); sign in again."
        )
    with open_context(config, session=session) as context:
        page = active_page(context)
        goto(page, INDEED_MY_JOBS, config)
        page.wait_for_timeout(2000)
        if "secure.indeed.com/auth" in page.url:
            store.mark(session, "revoked", reason="Indeed redirected saved cookies to sign-in")
            raise SessionMissingError("Indeed rejected the saved cookies; sign in again.")
        refreshed = capture_session(store, context, page, source="refresh", notes=("verified",))
        console.print("[green]Saved session is still accepted by Indeed.[/green]")
        return refreshed
