"""Shared test fixtures.

The tests run against the **real** state directory in the repository, so they
assert the real numbers (98 jobs, 5 runs, 5 messages).  The tests that need
a different dataset (an empty ledger, for instance) build a temporary state
directory and point ``INDEED_STATE_DIR`` at it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = Path(__file__).resolve().parents[1]

for candidate in (str(REPO_ROOT), str(API_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.main import app
from app.paths import get_config


@pytest.fixture(scope="session")
def state_dir() -> Path:
    """The real state directory of this repository."""
    return get_config().state_dir


@pytest.fixture(scope="session")
def client() -> TestClient:
    """A test client for the real application."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def temp_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An empty state directory, with ``INDEED_STATE_DIR`` pointing at it."""
    root = tmp_path / "data"
    (root / "master").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "cookies").mkdir(parents=True)
    monkeypatch.setenv("INDEED_STATE_DIR", str(root))
    return root


@pytest.fixture
def temp_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """A client bound to an empty state directory."""
    root = tmp_path / "data"
    (root / "master").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "cookies").mkdir(parents=True)
    monkeypatch.setenv("INDEED_STATE_DIR", str(root))
    with TestClient(app) as test_client:
        yield test_client


def write_json(path: Path, payload: object) -> None:
    """Write a JSON file, creating the parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write a JSONL file, creating the parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


@pytest.fixture
def write_helpers():
    """The JSON writers, for tests that build their own state."""
    return write_json, write_jsonl


@pytest.fixture(autouse=True)
def _no_writes_to_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test run if anything tries to write under the state directory.

    The backend is read-only: a stray ``mkdir`` or ``write_text`` under
    ``data/`` would be a contract violation, so the write path of the real
    state directory is made to fail loudly.
    """
    real_state = get_config().state_dir
    original_mkdir = Path.mkdir
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_open = Path.open

    def guard(path: Path) -> None:
        resolved = Path(path).resolve()
        if resolved == real_state or real_state in resolved.parents:
            raise AssertionError(f"the API must not write to the state directory: {resolved}")

    def guarded_mkdir(self: Path, *args, **kwargs):
        guard(self)
        return original_mkdir(self, *args, **kwargs)

    def guarded_write_text(self: Path, *args, **kwargs):
        guard(self)
        return original_write_text(self, *args, **kwargs)

    def guarded_write_bytes(self: Path, *args, **kwargs):
        guard(self)
        return original_write_bytes(self, *args, **kwargs)

    def guarded_open(self: Path, *args, **kwargs):
        mode = kwargs.get("mode", args[0] if args else "r")
        if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+")):
            guard(self)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    monkeypatch.setattr(Path, "open", guarded_open)
    os.environ.setdefault("INDEED_TESTING", "1")
