"""``GET /api/applications`` and ``/api/applications/summary``.

A missing ledger file is not an error: both endpoints return HTTP 200 with an
empty collection.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import paths
from app.models import ApplicationEntry, ApplicationListResponse, ApplicationSummary
from app.services import applications as applications_service

router = APIRouter(tags=["applications"])


@router.get("/applications", response_model=ApplicationListResponse, summary="Application ledger")
def list_applications(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str = Query("", description="Exact match on the ledger status."),
) -> ApplicationListResponse:
    """The ledger entries, one per job (the last entry for a job wins)."""
    config = paths.get_config()
    total, items = applications_service.list_applications(config, limit, offset, status)
    return ApplicationListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[ApplicationEntry(**item) for item in items],
    )


@router.get(
    "/applications/summary",
    response_model=ApplicationSummary,
    summary="Counts by ledger status",
)
def applications_summary() -> ApplicationSummary:
    """How many applications sit in each ledger status."""
    config = paths.get_config()
    return ApplicationSummary(**applications_service.summary(config))
