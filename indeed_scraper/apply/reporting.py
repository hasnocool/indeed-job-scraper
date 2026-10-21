"""Result reporting for the application flow."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import ApplyResult

RESULT_FIELDS = (
    "Job ID",
    "Fingerprint",
    "Company",
    "Title",
    "Location",
    "JobLink",
    "Portal",
    "Status",
    "Detail",
    "Applied At",
)


def write_apply_results(results: Sequence[ApplyResult], path: Path) -> Path:
    """Write the outcome of a run to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RESULT_FIELDS))
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "Job ID": result.app_id,
                    "Fingerprint": result.fingerprint,
                    "Company": result.company,
                    "Title": result.title,
                    "Location": result.location,
                    "JobLink": result.url,
                    "Portal": result.portal,
                    "Status": result.status,
                    "Detail": result.detail,
                    "Applied At": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
    return path


def load_ledger(path: Path) -> list[dict[str, Any]]:
    """Read the application ledger, skipping malformed lines."""
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
