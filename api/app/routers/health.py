"""``GET /api/health`` -- liveness and the resolved state directory."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__, paths
from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health() -> HealthResponse:
    """Always HTTP 200 while the process is up."""
    config = paths.get_config()
    return HealthResponse(
        status="ok",
        version=__version__,
        state_dir=str(config.state_dir),
    )
