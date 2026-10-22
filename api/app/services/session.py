"""Cookie session metadata.

**Safety rule 1**: this module never returns a cookie ``value`` and never
returns the ``user_agent``.  It parses ``data/cookies/current.json`` with the
scraper's own ``CookieSession`` model and reduces it to counts, ids,
timestamps and expiry.

The ``CookieStore`` class is deliberately not used: its constructor calls
``config.ensure_dirs()``, which would create directories under ``data/`` --
something a read-only backend must never do.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import paths
from app.services.cache import FileCache
from indeed_scraper.cookies import CookieSession

__all__ = ["session_info"]

_cache = FileCache()

#: The cookie names that carry the Indeed authentication, per contract 4.5.
#: The scraper's own ``AUTH_COOKIE_NAMES`` is a superset (it also counts the
#: Passport bearer family); the contract names these eight explicitly, so
#: the contract's list wins here.
CONTRACT_AUTH_COOKIE_NAMES = frozenset(
    {"SESS", "CTK", "SUB", "LV", "LD", "UIMF", "IRS", "CSRF"}
)


def _iso(value: Any) -> str:
    """A timestamp as it is stored on disk, without reformatting it."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return ""


def _load_session(config) -> CookieSession | None:
    """Parse the session file, or return ``None`` when there is none."""
    path = paths.cookie_file(config)

    def loader() -> CookieSession | None:
        if not path.is_file():
            return None
        try:
            return CookieSession.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    return _cache.get(path, loader)


def _auth_cookies(session: CookieSession) -> tuple[Any, ...]:
    """The auth cookies the contract counts."""
    return tuple(c for c in session.cookies if c.name in CONTRACT_AUTH_COOKIE_NAMES)


def _expires_at(session: CookieSession) -> datetime | None:
    """The earliest expiry among the auth cookies, or ``None``.

    A browser-session cookie has no expiry, so it is skipped: the session as a
    whole then has no known expiry.
    """
    stamps = [c.expires_at for c in _auth_cookies(session) if c.expires_at is not None]
    return min(stamps) if stamps else None


def session_info(config) -> dict[str, Any]:
    """The session metadata for ``GET /api/session``.

    With no session file the result is the contract's "no session" shape:
    ``has_session`` false, empty id, status ``none``, zero counts, no expiry.
    """
    session = _load_session(config)
    if session is None:
        return {
            "has_session": False,
            "session_id": "",
            "status": "none",
            "source": "",
            "created_at": "",
            "updated_at": "",
            "cookie_count": 0,
            "auth_cookie_count": 0,
            "expires_at": None,
            "expired": False,
        }

    expiry = _expires_at(session)
    expired = False
    if expiry is not None:
        expired = expiry < datetime.now(tz=timezone.utc)

    return {
        "has_session": True,
        "session_id": session.id,
        "status": session.status,
        "source": session.source,
        "created_at": _iso(session.created_at),
        "updated_at": _iso(session.updated_at),
        "cookie_count": len(session.cookies),
        "auth_cookie_count": len(_auth_cookies(session)),
        "expires_at": expiry.isoformat() if expiry is not None else None,
        "expired": expired,
    }
