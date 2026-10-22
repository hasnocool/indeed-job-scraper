"""Guard against leaking the live Indeed cookie credential.

``data/cookies/current.json`` holds a working Indeed sign-in.  Contract rule
1 forbids any cookie ``value`` (and the ``user_agent``) from appearing in a
response body, a log line, or an error message.

Three layers of defence:

1. **Design.**  The session service never reads a cookie ``value`` at all --
   it parses the file into the scraper's own ``CookieSession`` model and only
   ever returns counts, ids, timestamps and expiry.
2. **Runtime guard.**  :func:`assert_no_secrets` inspects a response body
   before it leaves the process.  It knows the real cookie values (read
   straight from the state directory) and refuses to let any of them through.
3. **Tests.**  ``api/tests/test_safety.py`` asserts that no endpoint's
   response contains a cookie value.

The guard never logs what it found: a leak is reported by *count* only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

__all__ = [
    "SecretLeakError",
    "assert_no_secrets",
    "cookie_values",
    "scan_for_secrets",
]

logger = logging.getLogger("api.safety")

#: Keys whose presence in a response body is treated as a cookie leak.
FORBIDDEN_KEYS = frozenset({"value", "user_agent", "userAgent", "cookie_values"})

#: A cookie value shorter than this is too generic to search for in a body
#: without false positives (the real file has one-character values).
MIN_SECRET_LENGTH = 8


class SecretLeakError(RuntimeError):
    """Raised when a response body would expose a cookie credential."""


def cookie_values(path: Path) -> list[str]:
    """Every cookie value stored in the session file.

    Used only by the guard, to know what must never escape.  The values are
    never returned to a caller and never logged.
    """
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    cookies = payload.get("cookies")
    if not isinstance(cookies, list):
        return []
    values: list[str] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        value = cookie.get("value")
        if isinstance(value, str) and len(value) >= MIN_SECRET_LENGTH:
            values.append(value)
    return values


def _walk(node: Any) -> list[dict[str, Any]]:
    """Every mapping nested anywhere inside a decoded JSON document."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(_walk(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_walk(value))
    return found


def scan_for_secrets(body: bytes, secrets: list[str]) -> list[str]:
    """Return the names of the problems found in ``body``.

    A problem is either a forbidden key (such as a cookie ``value``) or the
    verbatim appearance of a known cookie value.  The *values* are never
    included in the result -- only the key names and a marker, so the finding
    can be logged safely.
    """
    problems: list[str] = []
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("utf-8", errors="replace")

    try:
        document = json.loads(text)
    except ValueError:
        document = None

    if document is not None:
        for mapping in _walk(document):
            for key in mapping:
                if key in FORBIDDEN_KEYS:
                    problems.append(f"forbidden key: {key}")
    else:
        # Not JSON: fall back to a textual check for the key names.
        for key in FORBIDDEN_KEYS:
            if f'"{key}"' in text:
                problems.append(f"forbidden key: {key}")

    for secret in secrets:
        if secret and secret in text:
            problems.append("known cookie value")
            break

    return problems


def assert_no_secrets(body: bytes, secrets: list[str], *, context: str) -> None:
    """Raise :class:`SecretLeakError` when ``body`` exposes a credential.

    The error message names the *kind* of problem and the request context,
    never the value that leaked.
    """
    problems = scan_for_secrets(body, secrets)
    if not problems:
        return
    unique = sorted(set(problems))
    logger.error(
        "blocked a response for %s: %d forbidden pattern(s): %s",
        context,
        len(unique),
        ", ".join(unique),
    )
    raise SecretLeakError(
        f"response for {context} was blocked: it contained {', '.join(unique)}"
    )
