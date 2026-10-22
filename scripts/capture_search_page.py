"""Read-only, single-fetch capture of a live Indeed search-results page.

The captured HTML is committed as a test fixture so the extractor can be
fixed against the REAL DOM rather than a guess. Strict safety rules:

* Exactly ONE page fetch. No pagination, no clicking, no scrolling, no retries.
* Runs against a TEMPORARY state dir (default /tmp/capture-state). The repo's
  data/chrome-profile and data/cookies are never written.
* Session cookies are seeded (read-only) from data/cookies/current.json; cookie
  values are never printed, logged, or written to any file.
* If Indeed challenges, expires, or refuses the session: stop, report the
  blocker, exit non-zero, and do NOT write a fixture.

Usage:
    python3 scripts/capture_search_page.py \\
        --url "https://ca.indeed.com/jobs?q=&l=Ucluelet%2C%20BC&sort=date" \\
        --out tests/fixtures/indeed_search_page.html \\
        --state-dir /tmp/capture-state \\
        --cookies data/cookies/current.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
COOKIE_HEADER_RE = re.compile(r"(?i)(cookie|set-cookie|cf_clearance)\s*[:=]")
FORBIDDEN_TOKENS = ("cf_clearance", "PASS", "SESS")

DEFAULT_URL = "https://ca.indeed.com/jobs?q=&l=Ucluelet%2C%20BC&sort=date"
DEFAULT_OUT = "tests/fixtures/indeed_search_page.html"
DEFAULT_STATE_DIR = "/tmp/capture-state"
DEFAULT_COOKIES = "data/cookies/current.json"


def _seed_cookies(context, cookies_path: Path) -> int:
    """Seed the browser context with saved session cookies (read-only source)."""
    data = json.loads(cookies_path.read_text(encoding="utf-8"))
    cookies = data.get("cookies", data if isinstance(data, list) else [])
    payload = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        entry = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
        }
        for key in ("expires", "httpOnly", "secure", "sameSite"):
            if key in c and c[key] is not None:
                entry[key] = c[key]
        if entry["name"] and entry["value"]:
            payload.append(entry)
    if payload:
        context.add_cookies(payload)
    return len(payload)


def _sanitise(html: str) -> str:
    """Strip inline script/style and any cookie/header / personal material."""
    # Remove inline script blocks entirely.
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)
    # Remove inline style blocks (can carry injected tokens).
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", "", html)
    # Strip event-handler attributes (inline script surface).
    html = re.sub(r"\s(on\w+)=\"[^\"]*\"", "", html)
    html = re.sub(r"\s(on\w+)='[^\']*'", "", html)
    # Collapse any Authorization/Cookie header-looking lines.
    html = COOKIE_HEADER_RE.sub("REDACTED:", html)
    # Redact email addresses.
    html = EMAIL_RE.sub("redacted@example.invalid", html)
    return html


def _safe(html: str) -> tuple[bool, list[str]]:
    problems: list[str] = []
    for token in FORBIDDEN_TOKENS:
        if token.lower() in html.lower():
            problems.append(f"forbidden token present: {token}")
    if EMAIL_RE.search(html):
        problems.append("email address present")
    if COOKIE_HEADER_RE.search(html):
        problems.append("cookie/header header present")
    return (len(problems) == 0, problems)


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture one Indeed search page as a fixture.")
    ap.add_argument("--url", default=DEFAULT_URL, help="Search-results URL to fetch once.")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output fixture path.")
    ap.add_argument("--state-dir", default=DEFAULT_STATE_DIR, help="Temporary browser state dir.")
    ap.add_argument("--cookies", default=DEFAULT_COOKIES, help="Read-only cookie store to seed the session.")
    ap.add_argument("--headless", action="store_true", default=True, help="Run headless.")
    ap.add_argument("--no-headless", action="store_false", dest="headless", help="Show the browser window.")
    ap.add_argument("--wait-ms", type=int, default=3000, help="Milliseconds to wait after navigation.")
    args = ap.parse_args()

    cookies_path = Path(args.cookies)
    if not cookies_path.exists():
        print(f"blocked: cookie store not found: {cookies_path}", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless, args=["--no-sandbox"])
        try:
            context = browser.new_context(locale="en-US", no_viewport=True)
            try:
                seeded = _seed_cookies(context, cookies_path)
            except Exception as exc:  # noqa: BLE001
                print(f"blocked: could not seed session cookies: {exc}", file=sys.stderr)
                return 2
            page = context.new_page()
            try:
                page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:  # noqa: BLE001
                print(f"blocked: navigation refused: {exc}", file=sys.stderr)
                return 2
            page.wait_for_timeout(args.wait_ms)

            # Challenge / expiry detection — do not fight, do not retry.
            title = (page.title() or "").strip().lower()
            url = page.url or ""
            blocked = (
                "secure.indeed.com/auth" in url
                or "/auth?continue=" in url
                or title in {"just a moment...", "just a moment"}
                or "attention required" in title
                or title.startswith("blocked")
                or "security check" in title
                or "captcha" in title
                or "additional verification required" in (page.content() or "").lower()
            )
            if blocked:
                print(
                    "blocked: Indeed refused the session (auth wall / challenge / block page); "
                    "no fixture written.",
                    file=sys.stderr,
                )
                return 1

            html = page.content() or ""
        finally:
            with context:
                pass
            browser.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sanitised = _sanitise(html)
    ok, problems = _safe(sanitised)
    if not ok:
        print(f"blocked: fixture failed sanitisation: {'; '.join(problems)}", file=sys.stderr)
        return 3
    out_path.write_text(sanitised, encoding="utf-8")
    print(f"captured {len(sanitised)} bytes -> {out_path} (cookies seeded: {seeded})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
