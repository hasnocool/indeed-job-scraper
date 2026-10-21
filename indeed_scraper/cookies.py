"""Cookie capture, persistence and expiry tracking.

The store keeps three things:

cookies/current.json      the active session record (the cookie list in use)
cookies/sessions/*.json   every session snapshot ever captured
cookies/history.jsonl     append-only event log (saved / refreshed / expired)

Cookies are parsed at the browser boundary into typed records, so the rest of
the code never handles raw Playwright dictionaries.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import Config

SessionStatus = Literal["active", "expired", "revoked"]
SaveSource = Literal["login", "refresh", "import"]

SESSION_COOKIE_NAME = "SESS"
# Indeed no longer issues the legacy "SESS" cookie to every client. Current
# sessions are carried by the Passport bearer token (and its refresh token),
# so a signed-in browser is recognised by either family.
PASSPORT_COOKIE_NAMES: frozenset[str] = frozenset(
    {
        "__Secure-PassportAuthProxy-BearerToken",
        "__Secure-PassportAuthProxy-RefreshToken",
        "__Secure-PassportAuthProxy-OauthHMAC",
    }
)
SESSION_COOKIE_NAMES: frozenset[str] = frozenset({SESSION_COOKIE_NAME}) | PASSPORT_COOKIE_NAMES
AUTH_COOKIE_NAMES: frozenset[str] = frozenset(
    {"SESS", "CTK", "SUB", "LV", "LD", "UIMF", "IRS", "CSRF"}
) | PASSPORT_COOKIE_NAMES
INDEED_DOMAIN_SUFFIX = "indeed.com"
EXPIRY_SKEW_S = 120.0


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def is_indeed_domain(domain: str) -> bool:
    return domain.lstrip(".").endswith(INDEED_DOMAIN_SUFFIX)


class Cookie(BaseModel):
    """One browser cookie, mirroring Playwright's shape."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    name: str = Field(min_length=1)
    value: str
    domain: str = Field(min_length=1)
    path: str = "/"
    expires: float = -1.0
    http_only: bool = Field(default=False, alias="httpOnly")
    secure: bool = False
    same_site: Literal["Strict", "Lax", "None", ""] = Field(default="", alias="sameSite")

    @property
    def is_session_cookie(self) -> bool:
        return self.expires <= 0

    @property
    def expires_at(self) -> datetime | None:
        if self.expires <= 0:
            return None
        return datetime.fromtimestamp(self.expires, tz=timezone.utc)

    def to_playwright(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.model_dump(by_alias=True)
        if not payload["sameSite"]:
            payload.pop("sameSite")
        return payload


class CookieSession(BaseModel):
    """A named cookie list captured from a real browser session."""

    model_config = ConfigDict(frozen=True)

    id: str
    created_at: datetime
    updated_at: datetime
    source: SaveSource
    status: SessionStatus = "active"
    user_agent: str = ""
    notes: tuple[str, ...] = ()
    cookies: tuple[Cookie, ...] = ()

    def cookie(self, name: str) -> Cookie | None:
        return next((c for c in self.cookies if c.name == name), None)

    def session_cookie(self) -> Cookie | None:
        """The cookie that proves a signed-in session (legacy SESS or Passport)."""
        for name in sorted(SESSION_COOKIE_NAMES):
            found = self.cookie(name)
            if found is not None:
                return found
        return None

    def is_signed_in(self) -> bool:
        return self.session_cookie() is not None

    def auth_cookies(self) -> tuple[Cookie, ...]:
        return tuple(c for c in self.cookies if c.name in AUTH_COOKIE_NAMES)

    def expires_at(self) -> datetime | None:
        """Earliest expiry among the cookies that actually carry auth."""
        stamps = [c.expires_at for c in self.auth_cookies() if c.expires_at is not None]
        return min(stamps) if stamps else None

    def seconds_left(self, *, now: datetime | None = None) -> float | None:
        expiry = self.expires_at()
        if expiry is None:
            return None
        return (expiry - (now or utcnow())).total_seconds()

    def is_expired(self, *, now: datetime | None = None, skew_s: float = EXPIRY_SKEW_S) -> bool:
        if self.status != "active":
            return True
        left = self.seconds_left(now=now)
        return left is not None and left <= skew_s

    def playwright_cookies(self) -> list[dict[str, Any]]:
        return [c.to_playwright() for c in self.cookies]


def cookies_from_playwright(raw: list[dict[str, Any]]) -> tuple[Cookie, ...]:
    """Parse the browser's cookie dump into typed, Indeed-only records."""
    parsed: list[Cookie] = []
    for item in raw:
        try:
            cookie = Cookie.model_validate(item)
        except ValueError:
            continue
        if is_indeed_domain(cookie.domain):
            parsed.append(cookie)
    return tuple(parsed)


class CookieStore:
    """Durable, append-only cookie history plus the active session."""

    def __init__(self, config: Config) -> None:
        self._config = config
        config.ensure_dirs()

    @property
    def config(self) -> Config:
        return self._config

    def current(self) -> CookieSession | None:
        path = self._config.current_cookie_file
        if not path.is_file():
            return None
        try:
            return CookieSession.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    def require_current(self) -> CookieSession:
        from .errors import SessionMissingError

        session = self.current()
        if session is None:
            raise SessionMissingError(
                "No Indeed session saved yet. Run 'python -m indeed_scraper login'."
            )
        return session

    def save(
        self,
        *,
        cookies: tuple[Cookie, ...],
        source: SaveSource,
        user_agent: str = "",
        notes: tuple[str, ...] = (),
    ) -> CookieSession:
        now = utcnow()
        session = CookieSession(
            id=f"{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}",
            created_at=now,
            updated_at=now,
            source=source,
            user_agent=user_agent,
            notes=notes,
            cookies=cookies,
        )
        self._persist(session)
        self._append_history("saved", session, {"cookie_count": len(cookies)})
        return session

    def refresh(
        self,
        session: CookieSession,
        *,
        cookies: tuple[Cookie, ...],
        notes: tuple[str, ...] = (),
    ) -> CookieSession:
        """Persist rotated cookies under the same session id."""
        previous = {c.name: c.value for c in session.cookies}
        rotated = sorted({c.name for c in cookies if previous.get(c.name) != c.value})
        updated = session.model_copy(
            update={
                "cookies": cookies,
                "updated_at": utcnow(),
                "source": "refresh",
                "notes": session.notes + notes,
            }
        )
        self._persist(updated)
        self._append_history(
            "refreshed", updated, {"cookie_count": len(cookies), "rotated": rotated}
        )
        return updated

    def mark(self, session: CookieSession, status: SessionStatus, *, reason: str) -> CookieSession:
        updated = session.model_copy(
            update={
                "status": status,
                "updated_at": utcnow(),
                "notes": session.notes + (reason,),
            }
        )
        self._persist(updated)
        self._append_history(status, updated, {"reason": reason})
        return updated

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        path = self._config.history_file
        if not path.is_file() or limit < 1:
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:  # tiny log, clarity over micro-optimisation
                continue
        return events

    def snapshots(self) -> list[Path]:
        return sorted(self._config.sessions_dir.glob("*.json"))

    def _persist(self, session: CookieSession) -> None:
        text = session.model_dump_json(indent=2, by_alias=True)
        self._atomic_write(self._config.sessions_dir / f"{session.id}.json", text + "\n")
        self._atomic_write(self._config.current_cookie_file, text + "\n")

    def _append_history(
        self, event: str, session: CookieSession, extra: dict[str, Any]
    ) -> None:
        record: dict[str, Any] = {
            "event": event,
            "session_id": session.id,
            "at": utcnow().isoformat(),
            **extra,
        }
        path = self._config.history_file
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
