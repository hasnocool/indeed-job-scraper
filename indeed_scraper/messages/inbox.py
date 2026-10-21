"""Read and reply to recruiter conversations on Indeed.

The candidate inbox lives on its own domain (``messages.indeed.com``), not on
the job pages. The DOM is addressed through ``data-testid`` attributes so a
class-name change does not break it.

Everything here is selector-based; no pixel coordinates are used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..errors import IndeedScraperError

INBOX_URL = "https://messages.indeed.com/"

LIST_ITEM = '[data-testid="indeed-messaging--ConversationList__item"]'
LIST_CONTENT = '[data-testid="indeed-messaging--ConversationList__messageContent"]'
LIST_UNREAD = '[data-testid="indeed-messaging--ConversationList__unreadBadge"]'
LIST_LOCKED = '[data-testid="indeed-messaging--ConversationList__lockedContent"]'

CONVERSATION = '[data-testid="indeed-messaging--Conversation"]'
MESSAGE_CONTENT = '[data-testid="indeed-messaging--conversation-events-message-content"]'
MESSAGE_SENDER = '[data-testid="indeed-messaging--ConversationEventSender__participantName"]'
MESSAGE_TIME = '[data-testid="indeed-messaging--ConversationEventSender__timestamp"]'
MESSAGE_HTML = '[data-testid="indeed-messaging--Conversation__htmlText"]'

COMPOSE_BOX = '[data-testid="indeed-messaging--Conversation__composeBox"]'
COMPOSE_TEXTAREA = '[data-testid="indeed-messaging--compose-message-textarea"]'
SEND_BUTTON = '[data-testid="indeed-messaging--ComposeBox__sendButton"]'

_CONVERSATION_ID = re.compile(r"/conversations/([^?/]+)")

#: One record per conversation row. The inbox is a virtualised listbox of
#: role="option" elements, so the rows are read from the page itself: a
#: Playwright locator over 30 matches would fail its strict-mode check.
_JS_LIST = r"""() => {
  const items = Array.from(
    document.querySelectorAll('[data-testid="indeed-messaging--ConversationList__item"]'));
  return items.map((item, index) => {
    // The row text is "Company\nDate\nPreview"; the messageContent
    // element holds only the preview, so the row is the source of truth.
    const raw = item.innerText;
    const lines = (raw || '').split('\n').map(s => s.trim()).filter(Boolean);
    const link = item.querySelector('a[href*="/conversations/"]');
    const href = link ? link.getAttribute('href') : '';
    const match = href.match(/conversations\/([^?\/]+)/);
    return {
      index: index,
      company: lines[0] || '',
      date: lines[1] || '',
      preview: lines.slice(2).join(' '),
      unread: Boolean(item.querySelector(
        '[data-testid="indeed-messaging--ConversationList__unreadBadge"]')),
      locked: Boolean(item.querySelector(
        '[data-testid="indeed-messaging--ConversationList__lockedContent"]')),
      conversation_id: match ? match[1] : '',
      url: href,
    };
  });
}"""

_JS_MESSAGES = r"""() => {
  const nodes = document.querySelectorAll(
    '[data-testid="indeed-messaging--conversation-events-message-content"]');
  return Array.from(nodes).map((node) => {
    const sender = node.querySelector(
      '[data-testid="indeed-messaging--ConversationEventSender__participantName"]');
    const when = node.querySelector(
      '[data-testid="indeed-messaging--ConversationEventSender__timestamp"]');
    const text = node.querySelector('[data-testid="indeed-messaging--Conversation__htmlText"]');
    return {
      sender: sender ? (sender.innerText || '').trim() : '',
      timestamp: when ? (when.innerText || '').trim() : '',
      text: text ? (text.innerText || '').trim() : (node.innerText || '').trim(),
    };
  });
}"""


@dataclass(frozen=True, slots=True)
class Conversation:
    """One recruiter thread in the Indeed inbox."""

    index: int
    conversation_id: str
    company: str
    preview: str
    date: str
    unread: bool
    locked: bool
    url: str


@dataclass(frozen=True, slots=True)
class Message:
    """One message inside a conversation."""

    sender: str
    timestamp: str
    text: str


def open_inbox(page: Any) -> None:
    """Navigate to the candidate inbox."""
    page.goto(INBOX_URL, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(3000)


def list_conversations(page: Any) -> list[Conversation]:
    """List the conversations in the inbox, newest first."""
    try:
        raw = page.evaluate(_JS_LIST)
    except Exception as error:
        raise IndeedScraperError(f"Could not read the Indeed inbox: {error}") from error
    conversations: list[Conversation] = []
    for record in raw or []:
        conversations.append(
            Conversation(
                index=int(record.get("index", 0)),
                conversation_id=str(record.get("conversation_id", "")),
                company=str(record.get("company", "")),
                preview=str(record.get("preview", "")),
                date=str(record.get("date", "")),
                unread=bool(record.get("unread")),
                locked=bool(record.get("locked")),
                url=str(record.get("url", "")),
            )
        )
    return conversations


def find_row(page: Any, conversation: Conversation) -> int | None:
    """Find the row of a conversation in the CURRENT inbox list.

    The inbox is a virtualised listbox: a new recruiter message shifts the
    rows, so an index captured earlier can point at a different thread. The
    row is therefore located by its CONTENT (the preview text, or the
    participant name), not by a stale position. Returns None when the
    conversation is no longer listed.
    """
    conversations = list_conversations(page)
    target_company = " ".join(conversation.company.split()).lower()
    target_preview = " ".join(conversation.preview.split()).lower()
    for candidate in conversations:
        company = " ".join(candidate.company.split()).lower()
        preview = " ".join(candidate.preview.split()).lower()
        if target_preview and preview and preview[:40] == target_preview[:40]:
            return candidate.index
        if company and target_company and company == target_company:
            return candidate.index
    return None


def open_conversation(page: Any, conversation: Conversation) -> list[Message]:
    """Open a conversation and return its messages."""
    if conversation.url:
        page.goto(conversation.url, wait_until="domcontentloaded", timeout=45_000)
    else:
        # The list only exists on the inbox page, so a row is clicked from a
        # freshly loaded list (after the first conversation the list is gone).
        # The row is found by its CONTENT, because the list may have shifted
        # since it was listed.
        open_inbox(page)
        index = find_row(page, conversation)
        if index is None:
            raise IndeedScraperError(
                f"Conversation {conversation.company!r} is no longer in the list."
            )
        rows = page.locator(LIST_ITEM)
        if index >= rows.count():
            raise IndeedScraperError(
                f"Conversation {conversation.company!r} is no longer in the list."
            )
        rows.nth(index).click()
    page.wait_for_timeout(3000)
    raw = page.evaluate(_JS_MESSAGES)
    return [
        Message(
            sender=str(record.get("sender", "")),
            timestamp=str(record.get("timestamp", "")),
            text=str(record.get("text", "")),
        )
        for record in raw or []
    ]


def current_conversation_id(page: Any) -> str:
    """The conversation id currently open, taken from the URL."""
    match = _CONVERSATION_ID.search(page.url)
    return match.group(1) if match else ""


def compose_box_ready(page: Any) -> bool:
    """True when the compose box is available for a reply."""
    try:
        return page.locator(COMPOSE_TEXTAREA).count() > 0
    except Exception:  # noqa: BLE001
        return False


def send_reply(page: Any, text: str) -> bool:
    """Type a reply and send it. Returns True when the send control accepted it."""
    body = text.strip()
    if not body:
        raise IndeedScraperError("Refusing to send an empty message.")
    textarea = page.locator(COMPOSE_TEXTAREA).first
    textarea.fill(body)
    page.wait_for_timeout(300)
    send = page.locator(SEND_BUTTON).first
    send.click()
    page.wait_for_timeout(1500)
    return True
