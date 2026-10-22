"""``GET /api/runs`` -- the scrape-run history."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import paths
from app.models import RunInfo, RunListResponse
from app.services import runs as runs_service

router = APIRouter(tags=["runs"])


@router.get("/runs", response_model=RunListResponse, summary="Scrape run history")
def list_runs(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> RunListResponse:
    """The runs, newest first."""
    config = paths.get_config()
    total, items = runs_service.list_runs(config, limit, offset)
    return RunListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[RunInfo(**item) for item in items],
    )
