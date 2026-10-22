"""The FastAPI application.

The API is **read-only**: every route is a ``GET`` and nothing under ``data/``
is ever written.  The app is mounted under the ``/api`` prefix, so the
interactive docs live at ``/docs`` and the OpenAPI schema at
``/openapi.json``.

Safety rule 1 is enforced at runtime by :func:`app.safety.assert_no_secrets`:
a middleware inspects every response body before it leaves the process and
blocks one that would expose a cookie credential.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app import __version__, paths, settings
from app.routers import applications, health, jobs, messages, runs, session
from app.safety import assert_no_secrets, cookie_values

__all__ = ["app", "create_app"]

logger = logging.getLogger("api")

#: The API prefix required by the contract.
API_PREFIX = "/api"


def create_app() -> FastAPI:
    """Build the application."""
    application = FastAPI(
        title="Indeed Job Scraper API",
        version=__version__,
        description=(
            "Read-only backend over the Indeed job scraper's state directory. "
            "See docs/api-contract.md for the frozen contract."
        ),
        # The contract puts the interactive docs at /api/docs.
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )
    application.middleware("http")(secret_guard_middleware)

    for router in (
        health.router,
        jobs.router,
        session.router,
        runs.router,
        applications.router,
        messages.router,
    ):
        application.include_router(router, prefix=API_PREFIX)

    return application


async def secret_guard_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Refuse to let a cookie credential leave the process.

    The body of every response is checked for a cookie ``value`` key, a
    ``user_agent`` key, or the verbatim text of a stored cookie value.  A
    body that trips the check is replaced with a 500 that says nothing about
    what was found.
    """
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    config = paths.get_config()
    try:
        assert_no_secrets(body, cookie_values(paths.cookie_file(config)), context=str(request.url.path))
    except Exception as error:  # noqa: BLE001 - the guard must never leak the body
        logger.error("secret guard blocked a response: %s", type(error).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Response blocked by the credential guard."},
        )

    return Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=content_type,
    )


app = create_app()
