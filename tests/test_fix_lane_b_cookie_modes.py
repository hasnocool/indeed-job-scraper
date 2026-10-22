"""B6 - every file that can hold a session secret must be 0600.

``data/cookies/current.json`` holds the LIVE Indeed session: the ``SESS``
cookie and the Passport bearer token. ``data/cookies/history.jsonl`` records
the session's history, and ``data/cookies/sessions/<id>.json`` is a snapshot
of the same thing. Every one of them is a secret.

The old write path did:

    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
    os.chmod(path, 0o600)

The file was created by ``write_text``, so it inherited the process umask
(0644 with the usual umask 022) and was WORLD-READABLE until the chmod ran
afterwards. On a shared machine that is a window in which another local user
can read the operator's Indeed session token.

The fix: create the file 0600 BEFORE any content is written, so it is never
readable by anyone else - not even briefly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from indeed_scraper.config import Config
from indeed_scraper.cookies import CookieStore


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def _config(tmp_path: Path) -> Config:
    return Config.load(state_dir=tmp_path / "state")


def _session(store: CookieStore):
    from indeed_scraper.cookies import Cookie

    return store.save(
        cookies=(
            Cookie(name="SESS", value="s3cr3t-token", domain=".indeed.com"),
        ),
        source="login",
    )


def test_the_current_cookie_file_is_0600(tmp_path: Path) -> None:
    """The live session file must be private."""
    store = CookieStore(_config(tmp_path))
    _session(store)

    path = _config(tmp_path).current_cookie_file
    assert path.is_file()
    assert _mode(path) == 0o600, f"{path} is {oct(_mode(path))}, expected 0o600"


def test_the_session_snapshot_is_0600(tmp_path: Path) -> None:
    """The per-session snapshot holds the same secret."""
    store = CookieStore(_config(tmp_path))
    session = _session(store)

    path = _config(tmp_path).sessions_dir / f"{session.id}.json"
    assert path.is_file()
    assert _mode(path) == 0o600, f"{path} is {oct(_mode(path))}, expected 0o600"


def test_the_history_file_is_0600(tmp_path: Path) -> None:
    """The history file records the session too."""
    store = CookieStore(_config(tmp_path))
    _session(store)

    path = _config(tmp_path).history_file
    assert path.is_file()
    assert _mode(path) == 0o600, f"{path} is {oct(_mode(path))}, expected 0o600"


def test_the_cookie_directory_is_0700(tmp_path: Path) -> None:
    """The directory holding the secrets must not be listable by others."""
    store = CookieStore(_config(tmp_path))
    _session(store)

    assert _mode(_config(tmp_path).cookies_dir) == 0o700


def test_the_file_is_never_readable_before_the_content_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE WINDOW: no content may be written into a world-readable file.

    The mode must be 0600 from the moment the file is CREATED, so there is
    no instant at which the session token sits in a file another local user
    can read.

    The observer watches every way a secret file can be created - through
    ``os.open`` (the mode it was CREATED with) and through
    ``Path.write_text`` (the mode it has on disk when the content lands) -
    and records the mode of each.
    """
    store = CookieStore(_config(tmp_path))
    _session(store)

    observed: list[tuple[str, int]] = []
    real_open = os.open
    real_write_text = Path.write_text

    def _watched_open(path: str, flags: int, mode: int = 0o777, *args: object):
        fd = real_open(path, flags, mode, *args)  # type: ignore[arg-type]
        target = Path(path)
        if target.parent.name == "cookies" and target.suffix != ".lock":
            observed.append((target.name, target.stat().st_mode & 0o777))
        return fd

    def _watched_write_text(self: Path, *args: object, **kwargs: object) -> int:
        result = real_write_text(self, *args, **kwargs)  # type: ignore[arg-type]
        if self.parent.name == "cookies":
            observed.append((self.name, self.stat().st_mode & 0o777))
        return result

    monkeypatch.setattr(os, "open", _watched_open)
    monkeypatch.setattr(Path, "write_text", _watched_write_text)

    store.save(cookies=(), source="login")

    assert observed, "the write was not observed"
    bad = [entry for entry in observed if entry[1] != 0o600]
    assert not bad, (
        f"a secret was written into a file with mode {bad}; the file must "
        "be created 0600 BEFORE the content is written, never tightened "
        "afterwards"
    )


def test_an_existing_loose_cookie_file_is_tightened_on_write(
    tmp_path: Path,
) -> None:
    """A file left 0644 by an older run must be tightened, not inherited."""
    config = _config(tmp_path)
    store = CookieStore(config)
    store._config.ensure_dirs()

    path = config.current_cookie_file
    path.write_text('{"stale": true}\n', encoding="utf-8")
    os.chmod(path, 0o644)

    _session(store)

    assert _mode(path) == 0o600, (
        "an existing world-readable cookie file must be tightened to 0600"
    )


def test_the_temp_file_never_holds_a_readable_secret(tmp_path: Path) -> None:
    """The temporary file is 0600 too - it holds the same content."""
    config = _config(tmp_path)
    store = CookieStore(config)

    _session(store)

    leftovers = list(config.cookies_dir.glob("*.tmp"))
    for leftover in leftovers:
        assert _mode(leftover) == 0o600, leftover
