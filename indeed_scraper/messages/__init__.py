"""Manage recruiter conversations in the Indeed candidate inbox.

The inbox is a separate web app (``messages.indeed.com``) reached with the
same saved session as the scraper. This package reads the threads, classifies
each incoming message, builds a reply from the operator's profile, and sends it
when the autonomy policy allows.
"""

from __future__ import annotations

from .compose import MessageKind, ReplyPlan, build_reply, classify
from .inbox import (
    Conversation,
    Message,
    compose_box_ready,
    list_conversations,
    open_conversation,
    open_inbox,
    send_reply,
)
from .store import (
    already_replied,
    messages_dir,
    read_sent,
    record_sent,
    sent_ledger_path,
)

__all__ = [
    "Conversation",
    "Message",
    "MessageKind",
    "ReplyPlan",
    "already_replied",
    "build_reply",
    "classify",
    "compose_box_ready",
    "list_conversations",
    "messages_dir",
    "open_conversation",
    "open_inbox",
    "read_sent",
    "record_sent",
    "send_reply",
    "sent_ledger_path",
]
