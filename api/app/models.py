"""Response models mirroring the frozen TypeScript contract.

Every field name here is snake_case and identical to the interface of the
same name in ``docs/api-contract.md`` section 6.  Missing or empty values are
``""`` (never ``null``); empty lists are ``[]``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApplicationEntry",
    "ApplicationSummary",
    "HealthResponse",
    "Job",
    "JobFacets",
    "JobListResponse",
    "MessageEntry",
    "MessageListResponse",
    "RunInfo",
    "RunListResponse",
    "SessionInfo",
]


class HealthResponse(BaseModel):
    """``GET /api/health``."""

    status: str = "ok"
    version: str = "0.1.0"
    state_dir: str = ""


class Job(BaseModel):
    """One entry of the master dataset, returned verbatim."""

    model_config = ConfigDict(extra="ignore")

    jk: str
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    schedule: str = ""
    posted: str = ""
    snippet: str = ""
    url: str = ""
    matches: list[str] = Field(default_factory=list)
    fingerprint: str = ""
    short_id: str = ""
    status: str = ""
    first_seen: str = ""
    last_seen: str = ""
    seen_count: int = 0
    duplicate_of: str = ""


class JobListResponse(BaseModel):
    """``GET /api/jobs`` -- a filtered page of jobs."""

    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[Job] = Field(default_factory=list)


class JobFacets(BaseModel):
    """``GET /api/jobs/facets`` -- filter values for the UI dropdowns."""

    total: int = 0
    locations: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)


class SessionInfo(BaseModel):
    """``GET /api/session`` -- cookie session metadata only.

    No cookie value and no user agent ever appears here.
    """

    has_session: bool = False
    session_id: str = ""
    status: str = "none"
    source: str = ""
    created_at: str = ""
    updated_at: str = ""
    cookie_count: int = 0
    auth_cookie_count: int = 0
    expires_at: str | None = None
    expired: bool = False


class RunInfo(BaseModel):
    """One scrape run."""

    file: str = ""
    scraped_at: str = ""
    query: str = ""
    locations: list[str] = Field(default_factory=list)
    pages_fetched: int = 0
    total_jobs: int = 0
    stopped_reason: str = ""


class RunListResponse(BaseModel):
    """``GET /api/runs`` -- a page of scrape runs, newest first."""

    total: int = 0
    limit: int = 20
    offset: int = 0
    items: list[RunInfo] = Field(default_factory=list)


class ApplicationEntry(BaseModel):
    """One application-ledger entry."""

    jk: str = ""
    company: str = ""
    title: str = ""
    status: str = ""
    at: str = ""
    indeed_url: str = ""


class ApplicationListResponse(BaseModel):
    """``GET /api/applications`` -- a page of ledger entries."""

    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[ApplicationEntry] = Field(default_factory=list)


class ApplicationSummary(BaseModel):
    """``GET /api/applications/summary`` -- counts by ledger status."""

    total: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)


class MessageEntry(BaseModel):
    """One sent Indeed message."""

    conversation_id: str = ""
    company: str = ""
    kind: str = ""
    status: str = ""
    body: str = ""
    detail: str = ""
    at: str = ""


class MessageListResponse(BaseModel):
    """``GET /api/messages`` -- a page of sent messages, newest first."""

    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[MessageEntry] = Field(default_factory=list)
