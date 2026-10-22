"""``GET /api/messages`` -- the sent Indeed messages."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import paths
from app.models import MessageEntry, MessageListResponse
from app.services import messages as messages_service

router = APIRouter(tags=["messages"])


@router.get("/messages", response_model=MessageListResponse, summary="Sent messages")
def list_messages(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> MessageListResponse:
    """The sent messages, newest first."""
    config = paths.get_config()
    total, items = messages_service.list_messages(config, limit, offset)
    return MessageListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[MessageEntry(**item) for item in items],
    )
