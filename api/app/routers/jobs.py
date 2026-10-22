"""``GET /api/jobs``, ``/api/jobs/facets`` and ``/api/jobs/{short_id}``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import paths
from app.models import Job, JobFacets, JobListResponse
from app.services import jobs as jobs_service

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=JobListResponse, summary="Search the master dataset")
def list_jobs(
    q: str = Query("", description="Free-text search over title, company, location, snippet and salary."),
    location: str = Query("", description="Case-insensitive substring match on location."),
    company: str = Query("", description="Case-insensitive substring match on company."),
    status: str = Query("", description="Exact match on the job status: new, updated or unchanged."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("last_seen", description="One of last_seen, first_seen, title, company, salary."),
    order: str = Query("desc", description="asc or desc."),
) -> JobListResponse:
    """The master dataset, filtered and paginated.

    ``total`` is the count after filtering and before pagination.
    """
    config = paths.get_config()
    query = jobs_service.JobQuery(
        q=q,
        location=location,
        company=company,
        status=status,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    total, items = jobs_service.list_jobs(config, query)
    return JobListResponse(total=total, limit=limit, offset=offset, items=[Job(**item) for item in items])


@router.get("/jobs/facets", response_model=JobFacets, summary="Filter values for the dropdowns")
def job_facets() -> JobFacets:
    """The distinct locations, companies and status counts of the dataset."""
    config = paths.get_config()
    return JobFacets(**jobs_service.facets(config))


@router.get("/jobs/{short_id}", response_model=Job, summary="One job by its short id")
def get_job(short_id: str) -> Job:
    """One job by its 12-character ``short_id``.

    Returns 404 with ``{"detail": "Job not found"}`` when no job has it.
    """
    config = paths.get_config()
    job = jobs_service.find_by_short_id(config, short_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return Job(**job)
