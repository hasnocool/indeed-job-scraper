"""Session-wide test fixtures.

The most important thing in this file is the STATE-DIRECTORY GUARD.

``Config.load`` resolves its state directory from ``INDEED_STATE_DIR``, and
falls back to the repository's real ``data/`` directory when that variable
is not set. A test run must never write into the operator's real data: it
can clobber real application records, and it makes the suite's side
effects depend on the state of the working tree.

The guard is set for the WHOLE session, so it holds even for a test that
reaches the real config factory - a monkeypatch cannot be relied on to
reach a command whose closure captured the factory at import time.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _redirect_state_dir() -> Iterator[Path]:
    """Point every config at a temporary state directory for the session.

    The directory is created once for the session and removed at the end.
    Nothing a test does can reach the repository's ``data/`` directory
    while this fixture is active.
    """
    with tempfile.TemporaryDirectory(prefix="indeed-scraper-tests-") as tmp:
        state_dir = Path(tmp).resolve()
        previous = os.environ.get("INDEED_STATE_DIR")
        os.environ["INDEED_STATE_DIR"] = str(state_dir)
        try:
            yield state_dir
        finally:
            if previous is None:
                os.environ.pop("INDEED_STATE_DIR", None)
            else:
                os.environ["INDEED_STATE_DIR"] = previous
