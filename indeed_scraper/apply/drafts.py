"""Draft file helpers for application state."""

from __future__ import annotations

import json
import os
from pathlib import Path


def app_id_for(fingerprint: str) -> str:
    """Return the first 12 characters of a fingerprint as the app ID."""
    return fingerprint[:12]


def draft_path(root: Path, app_id: str) -> Path:
    """Return the draft file path for a given app ID."""
    return root / app_id / "draft.json"


def write_draft(root: Path, app_id: str, payload: dict) -> Path:
    """Write a draft atomically (temp + os.replace); create dirs 0700."""
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    p = draft_path(root, app_id)
    tmp = p.with_suffix(".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.chmod(0o600)
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()
    return p


def read_draft(root: Path, app_id: str) -> dict | None:
    """Read a draft; return None if the file does not exist."""
    p = draft_path(root, app_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None