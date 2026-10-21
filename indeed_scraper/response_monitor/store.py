"""Response storage for Indeed application tracking."""

import json
import os
from pathlib import Path

RESPONSE_STATUSES = ("applied", "viewed", "interview", "rejected", "withdrawn", "unknown")


def response_path(root: Path, app_id: str) -> Path:
    """Return the response file path for a given app_id under root."""
    return root / f"{app_id}.json"


def write_response(root: Path, app_id: str, payload: dict) -> Path:
    """Atomically write a response payload to root/<app_id>.json with mode 0600.

    Uses a temp file + os.replace for atomicity.
    """
    path = response_path(root, app_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    return path


def read_response(root: Path, app_id: str):
    """Read a response file; return dict or None if missing/invalid."""
    path = response_path(root, app_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def list_responses(root: Path) -> list[dict]:
    """List all response dicts under root, skipping missing/invalid files."""
    records: list[dict] = []
    if not root.is_dir():
        return records
    for child in root.iterdir():
        if child.is_file() and child.suffix == ".json":
            try:
                data = json.loads(child.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    records.append(data)
            except (json.JSONDecodeError, OSError):
                continue
    return records