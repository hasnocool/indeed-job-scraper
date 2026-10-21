"""Regression tests for detecting a signed-in Indeed session.

Indeed stopped issuing the legacy "SESS" cookie; current sessions are carried
by the Passport bearer token. Detection must accept both families, and must
not treat anonymous or foreign-domain cookies as a session.
"""

from __future__ import annotations

from datetime import datetime, timezone

from indeed_scraper.auth import has_sign_in_cookie
from indeed_scraper.cookies import SESSION_COOKIE_NAMES, Cookie, CookieSession

PASSPORT = "__Secure-PassportAuthProxy-BearerToken"


def _cookie(name: str, domain: str = ".indeed.com") -> Cookie:
    return Cookie(name=name, value="value", domain=domain, path="/")


class _Context:
    """Minimal stand-in for a Playwright browser context.

    Playwright returns cookies as plain dicts, which is the shape that broke
    the original detector (it read attributes instead of keys).
    """

    def __init__(self, cookies: list[Cookie] | list[dict[str, object]]) -> None:
        self._cookies = cookies

    def cookies(self) -> list[Cookie] | list[dict[str, object]]:
        return self._cookies


def _playwright_cookie(name: str, domain: str = ".indeed.com") -> dict[str, object]:
    return {"name": name, "value": "value", "domain": domain, "path": "/"}


def test_playwright_dict_cookie_is_detected() -> None:
    assert has_sign_in_cookie(_Context([_playwright_cookie(PASSPORT)])) is True


def test_playwright_dict_legacy_sess_is_detected() -> None:
    assert has_sign_in_cookie(_Context([_playwright_cookie("SESS")])) is True


def test_playwright_dict_anonymous_cookies_are_not_a_session() -> None:
    anonymous = [_playwright_cookie("CTK"), _playwright_cookie("SURF")]
    assert has_sign_in_cookie(_Context(anonymous)) is False


def test_passport_bearer_token_counts_as_signed_in() -> None:
    assert has_sign_in_cookie(_Context([_cookie(PASSPORT)])) is True


def test_legacy_sess_cookie_still_counts_as_signed_in() -> None:
    assert has_sign_in_cookie(_Context([_cookie("SESS")])) is True


def test_anonymous_cookies_are_not_a_session() -> None:
    anonymous = [_cookie("CTK"), _cookie("SURF"), _cookie("FPID")]
    assert has_sign_in_cookie(_Context(anonymous)) is False


def test_session_cookie_from_another_domain_is_ignored() -> None:
    foreign = _cookie(PASSPORT, domain=".example.com")
    assert has_sign_in_cookie(_Context([foreign])) is False


def test_context_without_cookies_callable_is_not_a_session() -> None:
    assert has_sign_in_cookie(object()) is False


def test_saved_session_reports_signed_in_from_passport_cookie() -> None:
    now = datetime.now(tz=timezone.utc)
    session = CookieSession(
        id="20261021-000000-abcdef",
        created_at=now,
        updated_at=now,
        source="login",
        cookies=(_cookie(PASSPORT),),
    )
    assert session.is_signed_in() is True
    assert session.session_cookie() is not None
    assert session.session_cookie().name == PASSPORT


def test_passport_names_are_registered_as_session_cookies() -> None:
    assert PASSPORT in SESSION_COOKIE_NAMES
    assert "SESS" in SESSION_COOKIE_NAMES
