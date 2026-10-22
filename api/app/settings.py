"""Runtime settings for the API server.

The port moved to 8001 because 8000 is already taken on this machine by an
unrelated service.  Both the host and the port are overridable through the
environment so nothing is hard-coded:

``API_HOST``     interface to bind (default ``127.0.0.1``)
``API_PORT``     TCP port to bind (default ``8001``)
``API_CORS_ORIGINS``  comma-separated allowed origins
"""

from __future__ import annotations

import os

__all__ = [
    "DEFAULT_CORS_ORIGINS",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "api_host",
    "api_port",
    "cors_origins",
]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


def api_host() -> str:
    """The interface uvicorn should bind."""
    return os.environ.get("API_HOST", "").strip() or DEFAULT_HOST


def api_port() -> int:
    """The TCP port uvicorn should bind."""
    raw = os.environ.get("API_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def cors_origins() -> list[str]:
    """The browser origins allowed to call the API.

    The Vite dev server proxies ``/api`` to the backend, so CORS is not needed
    for the normal development setup.  It is enabled anyway so the frontend
    can talk to the API directly.
    """
    raw = os.environ.get("API_CORS_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)
