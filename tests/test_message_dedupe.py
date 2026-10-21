"""A conversation must never receive two replies.

The conversation id is only known AFTER a conversation is opened: it appears
in the URL once the row is clicked. The dedupe check therefore has to run
after that point. Checked earlier, it compares against an empty id, never
matches, and the recruiter gets a second reply.

These tests pin the ORDER, not just the behaviour of the helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from indeed_scraper.apply.autonomy import AutonomyPolicy
from indeed_scraper.apply.profile import Profile
from indeed_scraper.messages import flow as flow_module
from indeed_scraper.messages.inbox import Conversation, Message


class _FakeContext:
    def __init__(self) -> None:
        self.pages: list[Any] = [object()]


class _FakeDriver:
    def __init__(self, context: _FakeContext) -> None:
        self._context = context

    def __enter__(self) -> tuple[_FakeContext, Any]:
        return self._context, type("Info", (), {"kind": "fake", "endpoint": "fake"})()

    def __exit__(self, *args: object) -> None:
        return None


def _profile(tmp_path: Path) -> Profile:
    return Profile(
        name="Brad Cooper",
        email="brad@example.com",
        phone="250-555-0142",
        resume_path=str(tmp_path / "resume.pdf"),
    )


def _conversation(index: int = 0) -> Conversation:
    return Conversation(
        index=index,
        conversation_id="",  # the list carries no id: it is only in the URL
        company="Acme Recruiting",
        preview="Hi Brad, I found your resume on Indeed.",
        date="Oct 1",
        unread=False,
        locked=False,
        url="",
    )


def _install_fakes(
    monkeypatch: Any,
    tmp_path: Path,
    conversation_id: str,
    sent: list[str],
) -> Any:
    """Replace the browser with a fake that reports a fixed conversation id."""

    monkeypatch.setattr(flow_module, "open_driver", lambda config, session: _FakeDriver(_FakeContext()))
    monkeypatch.setattr(flow_module, "open_inbox", lambda page: None)
    monkeypatch.setattr(flow_module, "list_conversations", lambda page: [_conversation()])
    monkeypatch.setattr(
        flow_module,
        "open_conversation",
        lambda page, conversation: [
            Message(sender="Acme Recruiting", timestamp="Oct 1", text="Hi Brad, I found your resume."),
        ],
    )
    monkeypatch.setattr(flow_module, "current_conversation_id", lambda page: conversation_id)

    def _send(page: Any, text: str) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr(flow_module, "send_reply", _send)

    class _Store:
        def current(self) -> Any:
            return type("Session", (), {"is_signed_in": lambda self: True})()

    monkeypatch.setattr(flow_module, "CookieStore", lambda config: _Store())
    return _Store()


def test_a_conversation_that_already_got_a_reply_is_skipped(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The second run must not answer the same recruiter twice."""
    from indeed_scraper.messages.store import record_sent

    conversation_id = "conv-already-answered"
    sent: list[str] = []
    store = _install_fakes(monkeypatch, tmp_path, conversation_id, sent)

    # The first run answered this conversation.
    record_sent(
        tmp_path,
        conversation_id=conversation_id,
        company="Acme Recruiting",
        body="Hello,",
        status="sent",
    )

    store = _install_fakes(monkeypatch, tmp_path, conversation_id, sent)

    outcomes = flow_module.handle_inbox(
        type("Config", (), {"state_dir": tmp_path})(),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        type("Console", (), {"print": lambda *a, **k: None})(),  # type: ignore[arg-type]
        profile=_profile(tmp_path),
        policy=AutonomyPolicy(level="full"),
        limit=5,
    )

    assert sent == [], "a second reply was sent to a conversation that already had one"
    assert [outcome.action for outcome in outcomes] == ["skipped"]
    assert outcomes[0].detail == "already replied"


def test_a_new_conversation_is_answered_once(tmp_path: Path, monkeypatch: Any) -> None:
    """The guard must not block a conversation that has never been answered."""
    sent: list[str] = []
    store = _install_fakes(monkeypatch, tmp_path, "conv-brand-new", sent)

    outcomes = flow_module.handle_inbox(
        type("Config", (), {"state_dir": tmp_path})(),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        type("Console", (), {"print": lambda *a, **k: None})(),  # type: ignore[arg-type]
        profile=_profile(tmp_path),
        policy=AutonomyPolicy(level="full"),
        limit=5,
    )

    assert len(sent) == 1, "the new conversation was not answered"
    assert [outcome.action for outcome in outcomes] == ["sent"]
