"""Persist the messages the agent has seen, drafted and sent.

Everything lives under ``data/messages/`` (git-ignored, like the rest of the
application state) so the conversation history survives a run and a reply can
be traced back to the message that caused it.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MESSAGES_DIRNAME = "messages"
LEDGER_FILENAME = "sent.jsonl"


def messages_dir(state_dir: Path) -> Path:
    """The messages workspace (created on demand)."""
    path = state_dir / MESSAGES_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def sent_ledger_path(state_dir: Path) -> Path:
    """The append-only log of what was sent or drafted."""
    return messages_dir(state_dir) / LEDGER_FILENAME


def now_iso() -> str:
    """The current UTC time, ISO 8601."""
    return datetime.now(tz=timezone.utc).isoformat()


def record_sent(
    state_dir: Path,
    *,
    conversation_id: str,
    company: str,
    body: str,
    status: str,
    kind: str = "",
    detail: str = "",
) -> Path:
    """Append one entry to the sent/drafted ledger.

    The body is stored: it is the operator's own message to a recruiter, and
    the history is what makes an autonomous reply accountable.
    """
    path = sent_ledger_path(state_dir)
    entry = {
        "conversation_id": conversation_id,
        "company": company,
        "kind": kind,
        "status": status,
        "body": body,
        "detail": detail,
        "at": now_iso(),
    }
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return path


def read_sent(state_dir: Path) -> list[dict[str, Any]]:
    """Read the sent/drafted ledger, skipping malformed lines."""
    path = sent_ledger_path(state_dir)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


#: A conversation is answered once. "sending" counts as answered: the
#: message may have gone out even if the run died before recording it, and
#: a second reply to the same recruiter is worse than a missed one.
ANSWERED_STATUSES = ("sent", "sending")


def already_replied(state_dir: Path, conversation_id: str) -> bool:
    """True when this conversation already received (or may have) a reply."""
    if not conversation_id:
        # An unknown conversation is treated as answered: fail closed.
        return True
    return any(
        entry.get("conversation_id") == conversation_id
        and entry.get("status") in ANSWERED_STATUSES
        for entry in read_sent(state_dir)
    )
