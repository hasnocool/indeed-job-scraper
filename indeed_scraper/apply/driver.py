"""Browser drivers for the application flow.

Two ways to get a browser that can actually reach Indeed:

``harness``
    Attach to the browser-harness MCP's own Chrome over CDP
    (``INDEED_HARNESS_CDP``, e.g. ``http://127.0.0.1:9222``). The harness
    browser is a long-lived, shared resource, so this driver never closes the
    browser itself - it only closes the tabs it opened.

``profile``
    Launch the repository's own persistent Chromium profile
    (``data/chrome-profile``), which carries the ``cf_clearance`` cookie and a
    warm fingerprint. Indeed's bot protection rejects the harness' headless
    browser even with a valid session, so this is the driver that works
    against Indeed.

Both drivers seed the saved Indeed session cookies from the cookie store, so
neither needs a second sign-in.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from ..config import Config
from ..cookies import CookieSession

HARNESS_CDP_ENV = "INDEED_HARNESS_CDP"
DEFAULT_HARNESS_CDP = "http://127.0.0.1:9222"


@dataclass(frozen=True, slots=True)
class DriverInfo:
    """Which driver is in use and where it points."""

    kind: str
    endpoint: str
    harness_reachable: bool


def harness_endpoint() -> str:
    """The configured browser-harness CDP endpoint ("" when unset)."""
    return os.environ.get(HARNESS_CDP_ENV, "").strip()


def _harness_context(pw: Any, endpoint: str, session: CookieSession) -> tuple[Any, Any]:
    """Attach to the harness browser and return (browser, context)."""
    browser = pw.chromium.connect_over_cdp(endpoint)
    contexts = browser.contexts
    context = contexts[0] if contexts else browser.new_context()
    if session.cookies:
        context.add_cookies(session.playwright_cookies())
    return browser, context


@contextmanager
def _harness_driver(
    endpoint: str, session: CookieSession
) -> Iterator[tuple[Any, DriverInfo]]:
    """Drive the harness browser, closing only the tabs we opened."""
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as pw:
        browser, context = _harness_context(pw, endpoint, session)
        info = DriverInfo(kind="harness", endpoint=endpoint, harness_reachable=True)
        try:
            yield context, info
        finally:
            for page in list(context.pages):
                if page.url == "about:blank":
                    page.close()
            try:
                browser.close()
            except Error:  # the shared browser may already be gone
                pass


@contextmanager
def open_driver(
    config: Config,
    session: CookieSession,
    *,
    headless: bool = False,
) -> Iterator[tuple[Any, DriverInfo]]:
    """Yield ``(context, info)`` for the apply flow to drive.

    Prefers the browser-harness browser when ``INDEED_HARNESS_CDP`` is set and
    the endpoint answers; otherwise falls back to the repository's own
    persistent profile.
    """
    from playwright.sync_api import Error

    endpoint = harness_endpoint()
    if endpoint:
        try:
            with _harness_driver(endpoint, session) as opened:
                yield opened
            return
        except Error:
            # The harness endpoint is unreachable: fall back to the local profile.
            pass

    from ..browser import open_context
    from ..errors import IndeedScraperError

    try:
        context_manager = open_context(config, session=session, headless=headless)
        context = context_manager.__enter__()
    except Error as error:
        raise IndeedScraperError(
            "Could not open the browser: "
            f"{error}. If the profile is locked by another Chromium, close it "
            "and remove the stale data/chrome-profile/Singleton* files."
        ) from error

    try:
        info = DriverInfo(
            kind="profile",
            endpoint=str(config.profile_dir),
            harness_reachable=bool(endpoint),
        )
        yield context, info
    finally:
        context_manager.__exit__(None, None, None)
