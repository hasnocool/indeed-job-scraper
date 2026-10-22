"""``GET /api/session`` -- cookie session metadata only.

See contract 4.5 and safety rule 1: no cookie value and no user agent ever
leaves this endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from app import paths
from app.models import SessionInfo
from app.services import session as session_service

router = APIRouter(tags=["session"])


@router.get("/session", response_model=SessionInfo, summary="Cookie session metadata")
def get_session() -> SessionInfo:
    """The session's metadata: ids, timestamps, counts and expiry.

    With no session file this is still HTTP 200, with ``has_session`` false.
    """
    config = paths.get_config()
    return SessionInfo(**session_service.session_info(config))
