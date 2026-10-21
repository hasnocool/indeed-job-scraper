"""Thin Playwright layer: one persistent browser profile, one challenge probe."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any, Literal

from .config import Config
from .cookies import CookieSession, cookies_from_playwright

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

INDEED_LOGIN = "https://secure.indeed.com/auth"
INDEED_MY_JOBS = "https://myjobs.indeed.com/"


def home_url(site: str) -> str:
    return f"https://{site}/"

_LAUNCH_ARGS = (
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
)

ChallengeKind = Literal[
    "none", "cloudflare_js", "cloudflare_block", "security_check", "verification", "captcha", "auth"
]


@contextmanager
def open_context(
    config: Config,
    *,
    headless: bool | None = None,
    session: CookieSession | None = None,
) -> Iterator[BrowserContext]:
    """Launch the persistent Chromium profile, optionally seeding saved cookies."""
    from playwright.sync_api import sync_playwright

    config.ensure_dirs()
    mode = config.headless if headless is None else headless
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            headless=mode,
            channel="chromium",
            args=list(_LAUNCH_ARGS),
            locale="en-US",
            no_viewport=True,
            slow_mo=0,
        )
        context.set_default_timeout(config.navigation_timeout_ms)
        try:
            if session is not None:
                seed_cookies(context, session)
            yield context
        finally:
            # The browser is a resource boundary: a failing close must not mask
            # the real error that is propagating out of the with-block.
            with suppress(Exception):
                context.close()


def active_page(context: BrowserContext) -> Page:
    return context.pages[0] if context.pages else context.new_page()


def seed_cookies(context: BrowserContext, session: CookieSession) -> bool:
    """Load saved cookies when the profile does not already hold a session."""
    names = {cookie["name"] for cookie in context.cookies()}
    if "SESS" in names:
        return False
    if not session.cookies:
        return False
    try:
        context.add_cookies(session.playwright_cookies())
    except Exception:  # noqa: BLE001
        return False
    return True


def goto(page: Page, url: str, config: Config) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=config.navigation_timeout_ms)


def is_auth_wall(url: str) -> bool:
    return "secure.indeed.com/auth" in url or "/auth?continue=" in url


def challenge_kind(page: Page) -> ChallengeKind:
    """Classify what is blocking the page, if anything."""
    if is_auth_wall(page.url):
        return "auth"
    lower = page.title().strip().lower()
    if lower in {"just a moment...", "just a moment"} or "attention required" in lower:
        return "cloudflare_js"
    if lower.startswith("blocked") and "indeed" in lower:
        return "cloudflare_block"
    if "security check" in lower:
        return "security_check"
    if "captcha" in lower:
        return "captcha"
    try:
        markup = page.content()
    except Exception:  # noqa: BLE001
        return "none"
    if "Additional Verification Required" in markup:
        return "verification"
    try:
        captcha = page.locator(
            'iframe[src*="captcha"], iframe[src*="hcaptcha"], .g-recaptcha, #captcha'
        )
        if captcha.count() > 0 and captcha.first.is_visible():
            return "captcha"
    except Exception:  # noqa: BLE001
        return "none"
    return "none"


def challenge_label(kind: ChallengeKind) -> str:
    labels = {
        "none": "no challenge",
        "cloudflare_js": "Cloudflare JavaScript check",
        "cloudflare_block": "Cloudflare block page",
        "security_check": "Indeed security check",
        "verification": "Indeed additional verification",
        "captcha": "CAPTCHA",
        "auth": "sign-in wall",
    }
    return labels[kind]


def wait_for_challenge(page: Page, *, timeout_s: float, poll_s: float = 3.0) -> ChallengeKind:
    """Wait while a challenge is displayed; a human solves it in headed mode."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        kind = challenge_kind(page)
        if kind == "none":
            return "none"
        if kind == "auth":
            return "auth"
        time.sleep(poll_s)
    return challenge_kind(page)


def cookies(context: BrowserContext, config: Config) -> tuple[Any, ...]:
    del config
    return cookies_from_playwright(context.cookies())
