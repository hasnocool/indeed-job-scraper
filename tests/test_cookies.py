"""Cookie store: persistence, rotation, expiry and parsing."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from indeed_scraper.config import Config
from indeed_scraper.cookies import Cookie, CookieStore, cookies_from_playwright, utcnow


@pytest.fixture
def store(tmp_path: Path) -> CookieStore:
    return CookieStore(Config.load(state_dir=tmp_path))


def cookie(name: str, value: str = "v1", *, expires: float = -1.0) -> Cookie:
    return Cookie(
        name=name,
        value=value,
        domain=".indeed.com",
        path="/",
        expires=expires,
        httpOnly=True,
        secure=True,
        sameSite="Lax",
    )


def expires_in(hours: float) -> float:
    return (utcnow() + timedelta(hours=hours)).timestamp()


def test_save_writes_current_session_and_history(store: CookieStore) -> None:
    session = store.save(
        cookies=(cookie("SESS", "abc", expires=expires_in(48)), cookie("CTK")),
        source="login",
        user_agent="test-agent",
    )

    assert store.current() is not None
    assert store.current().id == session.id  # type: ignore[union-attr]
    assert (store.config.sessions_dir / f"{session.id}.json").is_file()
    assert store.config.current_cookie_file.is_file()

    history = store.history()
    assert history[-1]["event"] == "saved"
    assert history[-1]["cookie_count"] == 2
    assert session.is_signed_in() is True


def test_current_is_none_without_a_file(store: CookieStore) -> None:
    assert store.current() is None


def test_expiry_uses_earliest_auth_cookie(store: CookieStore) -> None:
    session = store.save(
        cookies=(
            cookie("SESS", expires=expires_in(10)),
            cookie("CTK", expires=expires_in(2)),
            cookie("_sp_id", expires=expires_in(1)),
        ),
        source="login",
    )
    # _sp_id is not an auth cookie, so CTK (2h) drives the expiry.
    left = session.seconds_left()
    assert left is not None
    assert 7000 < left < 7300


def test_session_cookies_have_no_expiry(store: CookieStore) -> None:
    session = store.save(cookies=(cookie("SESS"), cookie("CTK")), source="login")
    assert session.expires_at() is None
    assert session.is_expired() is False


def test_expired_session_is_detected(store: CookieStore) -> None:
    session = store.save(cookies=(cookie("SESS", expires=expires_in(-1)),), source="login")
    assert session.is_expired() is True


def test_refresh_detects_rotated_cookies(store: CookieStore) -> None:
    session = store.save(
        cookies=(cookie("SESS", "old", expires=expires_in(24)),), source="login"
    )
    refreshed = store.refresh(
        session,
        cookies=(cookie("SESS", "new", expires=expires_in(24)), cookie("LV", "1")),
    )

    assert refreshed.id == session.id
    assert refreshed.cookie("SESS") is not None
    assert refreshed.cookie("SESS").value == "new"  # type: ignore[union-attr]
    events = store.history()
    assert events[-1]["event"] == "refreshed"
    assert events[-1]["rotated"] == ["LV", "SESS"]
    assert store.current().cookie("SESS").value == "new"  # type: ignore[union-attr]


def test_mark_expired_updates_status_and_history(store: CookieStore) -> None:
    session = store.save(cookies=(cookie("SESS"),), source="login")
    marked = store.mark(session, "revoked", reason="Indeed rejected it")

    assert marked.status == "revoked"
    assert store.current().status == "revoked"  # type: ignore[union-attr]
    assert store.history()[-1]["reason"] == "Indeed rejected it"


def test_cookies_from_playwright_keeps_only_indeed_domains() -> None:
    raw = [
        {"name": "SESS", "value": "x", "domain": ".indeed.com", "path": "/", "expires": -1,
         "httpOnly": True, "secure": True, "sameSite": "Lax"},
        {"name": "other", "value": "y", "domain": ".example.com", "path": "/", "expires": -1,
         "httpOnly": False, "secure": False, "sameSite": "None"},
        {"name": "SUB", "value": "z", "domain": "secure.indeed.com", "path": "/"},
    ]
    parsed = cookies_from_playwright(raw)
    assert [c.name for c in parsed] == ["SESS", "SUB"]
    assert parsed[1].http_only is False


def test_playwright_round_trip_preserves_fields() -> None:
    original = cookie("SESS", "abc", expires=1234.5)
    payload = original.to_playwright()
    restored = Cookie.model_validate(payload)
    assert restored == original


def test_corrupt_current_file_is_ignored(store: CookieStore) -> None:
    store.config.current_cookie_file.write_text("{not json", encoding="utf-8")
    assert store.current() is None


def test_snapshot_files_accumulate(store: CookieStore) -> None:
    store.save(cookies=(cookie("SESS", "a"),), source="login")
    store.save(cookies=(cookie("SESS", "b"),), source="login")
    assert len(store.snapshots()) == 2
    assert json.loads(store.config.history_file.read_text().splitlines()[0])["event"] == "saved"


def test_session_serializes_datetimes_as_iso(store: CookieStore) -> None:
    session = store.save(cookies=(cookie("SESS"),), source="login")
    raw = json.loads(store.config.current_cookie_file.read_text(encoding="utf-8"))
    assert datetime.fromisoformat(raw["created_at"]) == session.created_at
    assert raw["cookies"][0]["httpOnly"] is True
