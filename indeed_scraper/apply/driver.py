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
from ..errors import IndeedScraperError

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
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        _browser, context = _harness_context(pw, endpoint, session)
        info = DriverInfo(kind="harness", endpoint=endpoint, harness_reachable=True)
        # The harness browser is a SHARED resource: closing it would kill the
        # session other tools use, so it is only disconnected here. The flow
        # closes the tab it opened (see open_driver's callers).
        yield context, info


def _attach_harness(
    endpoint: str, session: CookieSession
) -> tuple[tuple[Any, DriverInfo, Any] | None, Exception | None]:
    """Attach to the harness browser, or report why it could not be reached.

    The connection is made EAGERLY, outside the generator's body, so that a
    failure to attach is reported as an attach failure and never as a failure
    of the caller's code. The harness browser is a shared resource: it is only
    disconnected, never closed.

    Returns ``((context, info, manager), None)`` on success and
    ``(None, cause)`` when the endpoint could not be reached.
    """
    from playwright.sync_api import Error

    manager = _harness_driver(endpoint, session)
    try:
        context, info = manager.__enter__()
    except Error as error:
        manager.__exit__(None, None, None)
        return None, error
    except BaseException:
        manager.__exit__(None, None, None)
        raise
    return (context, info, manager), None


@contextmanager
def open_driver(
    config: Config,
    session: CookieSession,
    *,
    headless: bool = False,
) -> Iterator[tuple[Any, DriverInfo]]:
    """Yield ``(context, info)`` for the apply flow to drive.

    Prefers the browser-harness browser when ``INDEED_HARNESS_CDP`` is set.

    Two rules matter here:

    * **Only the CONNECTION attempt may be caught.** ``contextlib`` implements
      a with-block by calling ``gen.throw(exc)``, so a ``yield`` placed
      INSIDE the ``try`` would route the CALLER's exception into the
      driver's ``except Error`` - the flow's own Playwright error would be
      swallowed and replaced, and the driver would fall back to the shared
      profile as a side effect. The harness is therefore attached EAGERLY,
      before the ``yield``.
    * **A configured harness endpoint that cannot be reached is an error,
      not a fallback.** The repository's ``data/chrome-profile`` browser is
      a differently-fingerprinted browser that carries the cf_clearance
      cookie; opening it because the harness crashed would be a surprise,
      and it is exactly the HC-7 risk of touching a shared profile. The
      operator gets a clear error and can decide what to do.
    """
    from playwright.sync_api import Error

    endpoint = harness_endpoint()
    if endpoint:
        attached, cause = _attach_harness(endpoint, session)
        if attached is None:
            raise IndeedScraperError(
                f"Could not attach to browser harness at {endpoint}"
                f"{f': {cause}' if cause else ''}. "
                f"Start the harness browser, or unset {HARNESS_CDP_ENV} to "
                "use the local profile driver."
            ) from cause
        context, info, manager = attached
        try:
            # The yield is OUTSIDE every try/except that catches a
            # Playwright Error, so an error raised by the flow reaches the
            # caller unchanged.
            yield context, info
        finally:
            manager.__exit__(None, None, None)
        return

    from ..browser import open_context

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
