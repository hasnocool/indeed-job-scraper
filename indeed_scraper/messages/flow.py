"""Drive the Indeed inbox: read the threads, answer the ones that can be answered.

The flow is policy-driven:

* ``manual`` - nothing is sent; every reply is recorded as a draft.
* ``auto``   - submissions are unattended, but replies are still drafted.
* ``full``   - replies are sent, EXCEPT a reply that accepts an offer or
  agrees to terms, which stays a draft unless the policy allows binding
  commitments.

Every decision is written to ``data/messages/sent.jsonl`` so an autonomous
reply can be audited afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.table import Table

from ..apply.autonomy import AutonomyPolicy
from ..apply.driver import open_driver
from ..apply.profile import Profile
from ..cookies import CookieStore
from .compose import build_reply, redact_operator
from .inbox import (
    Conversation,
    Message,
    current_conversation_id,
    list_conversations,
    open_conversation,
    open_inbox,
    send_reply,
)
from .store import already_replied, record_sent


@dataclass(frozen=True, slots=True)
class InboxOutcome:
    """What happened to one conversation."""

    company: str
    conversation_id: str
    action: str
    detail: str = ""


def _matches_listed(conversation: Conversation, messages: list[Message]) -> bool:
    """True when the opened thread is the conversation that was listed.

    The inbox is a virtualised listbox: a new recruiter message shifts the
    rows, so an index captured earlier can point at a DIFFERENT thread. The
    reply must go to the thread that was listed, so the opened thread is
    checked against the listing (preview text or participant name) before
    anything is sent.
    """
    preview = " ".join((conversation.preview or "").split()).lower()
    if preview:
        key = preview[:40]
        for message in messages:
            if key in " ".join(message.text.split()).lower():
                return True
    company = " ".join((conversation.company or "").split()).lower()
    if company:
        for message in messages:
            if company in " ".join(message.sender.split()).lower():
                return True
    return False


def _is_our_message(message: Message, profile: Profile) -> bool:
    """True when the message was written by the operator."""
    if not message.sender or not profile.name:
        return False
    name = profile.name.strip().lower()
    sender = message.sender.strip().lower()
    if sender == name:
        return True
    parts = [part for part in name.split() if part]
    return bool(parts) and parts[-1] in sender


def _latest_incoming(messages: list[Message], profile: Profile) -> Message | None:
    """The most recent message that did not come from the operator."""
    for message in reversed(messages):
        if not _is_our_message(message, profile):
            return message
    return None


def handle_inbox(
    config: Any,
    store: CookieStore,
    console: Console,
    *,
    profile: Profile,
    policy: AutonomyPolicy | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> list[InboxOutcome]:
    """Read the inbox and answer what the policy allows."""
    rules = policy or AutonomyPolicy()
    session = store.current()
    if session is None or not session.is_signed_in():
        from ..errors import SessionMissingError

        raise SessionMissingError("No signed-in Indeed session. Run 'login' first.")

    outcomes: list[InboxOutcome] = []
    with open_driver(config, session) as (context, info):
        console.print(f"[dim]driver: {info.kind} ({info.endpoint})[/dim]")
        existing = list(context.pages)
        page = existing[0] if existing else context.new_page()
        open_inbox(page)
        conversations = list_conversations(page)
        console.print(f"[dim]{len(conversations)} conversations in the inbox[/dim]")
        for conversation in conversations:
            if limit is not None and len(outcomes) >= limit:
                break
            if conversation.locked:
                continue
            try:
                messages = open_conversation(page, conversation)
                conversation_id = current_conversation_id(page) or conversation.conversation_id
            except Exception as error:  # noqa: BLE001
                outcomes.append(
                    InboxOutcome(conversation.company, conversation.conversation_id, "failed", str(error)[:80])
                )
                continue
            # The list order can change between listing and clicking, so the
            # opened thread is verified against the listing BEFORE anything
            # is sent. A mismatch means a different recruiter is open.
            if not _matches_listed(conversation, messages):
                outcomes.append(
                    InboxOutcome(
                        conversation.company,
                        conversation_id,
                        "skipped",
                        "the inbox list changed; the opened thread did not match",
                    )
                )
                continue
            if not conversation_id:
                # Without a stable id the conversation cannot be recognised
                # later, so replying now would risk answering it twice.
                outcomes.append(
                    InboxOutcome(
                        conversation.company,
                        "",
                        "skipped",
                        "the conversation id could not be determined",
                    )
                )
                continue
            # The conversation id is only known once the conversation is open
            # (it appears in the URL after the click), so the dedupe check
            # MUST happen here. Checking it earlier compares against an empty
            # id and never matches, which would reply twice.
            if already_replied(config.state_dir, conversation_id):
                outcomes.append(
                    InboxOutcome(conversation.company, conversation_id, "skipped", "already replied")
                )
                continue
            incoming = _latest_incoming(messages, profile)
            if incoming is None:
                outcomes.append(
                    InboxOutcome(conversation.company, conversation.conversation_id, "skipped", "no incoming message")
                )
                continue

            plan = build_reply(profile, incoming.text, conversation.company)
            may_send = rules.allows_reply and not dry_run
            if plan.requires_approval and not rules.allows_binding_commitment:
                may_send = False
            if not may_send:
                reason = "dry-run" if dry_run else (plan.reason or "policy requires approval")
                record_sent(
                    config.state_dir,
                    conversation_id=conversation_id,
                    company=conversation.company,
                    body=redact_operator(plan.body, profile),
                    status="drafted",
                    kind=plan.kind,
                    detail=reason,
                )
                outcomes.append(
                    InboxOutcome(
                        conversation.company,
                        conversation_id,
                        "drafted",
                        reason,
                    )
                )
                continue

            try:
                send_reply(page, plan.body)
            except Exception as error:  # noqa: BLE001
                record_sent(
                    config.state_dir,
                    conversation_id=conversation_id,
                    company=conversation.company,
                    body=plan.body,
                    status="failed",
                    kind=plan.kind,
                    detail=str(error)[:160],
                )
                outcomes.append(
                    InboxOutcome(conversation.company, conversation.conversation_id, "failed", str(error)[:80])
                )
                continue
            record_sent(
                config.state_dir,
                conversation_id=conversation_id,
                company=conversation.company,
                body=redact_operator(plan.body, profile),
                status="sent",
                kind=plan.kind,
            )
            console.print(f"[green]replied[/green] {conversation.company}: {plan.kind}")
            outcomes.append(
                InboxOutcome(conversation.company, conversation_id, "sent", plan.kind)
            )
    return outcomes


def print_outcomes(outcomes: list[InboxOutcome], console: Console) -> None:
    """Print a table of what happened to each conversation."""
    table = Table(title="Indeed inbox")
    table.add_column("Company")
    table.add_column("Action")
    table.add_column("Detail")
    for outcome in outcomes:
        table.add_row(outcome.company or "-", outcome.action, outcome.detail or "-")
    console.print(table)
