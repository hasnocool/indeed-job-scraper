"""Turn structured job records into JSON and CSV files."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dedupe import job_fingerprint, short_id
from .scraper import Job, ScrapeResult

CSV_FIELDS = (
    "Title",
    "Company",
    "Location",
    "Salary",
    "Schedule",
    "Posted Date",
    "Job Description",
    "JobLink",
    "Job Key",
    "Matched Locations",
    "Job ID",
    "Fingerprint",
    "Status",
    "First Seen",
    "Last Seen",
    "Seen Count",
    "Duplicate Of",
)

_LEGACY_KEYS = {
    "Title": ("title", "Title"),
    "Company": ("company", "Company"),
    "Location": ("location", "Location"),
    "Salary": ("salary", "Salary"),
    "Schedule": ("schedule", "Schedule"),
    "Posted Date": ("posted", "Posted Date"),
    "Job Description": ("snippet", "Job Description"),
    "JobLink": ("url", "JobLink"),
    "Job Key": ("jk", "Job Number"),
}


def _first(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def normalize_record(record: Mapping[str, Any]) -> dict[str, str]:
    """Map a structured or legacy record onto the CSV columns."""
    row: dict[str, str] = {}
    for field in CSV_FIELDS:
        if field == "Matched Locations":
            matches = record.get("matches")
            if isinstance(matches, (list, tuple)):
                row[field] = "; ".join(str(item) for item in matches)
            else:
                row[field] = str(matches or "")
        elif field in {
            "Job ID",
            "Fingerprint",
            "Status",
            "First Seen",
            "Last Seen",
            "Seen Count",
            "Duplicate Of",
        }:
            # New dedup columns: fall back to "" if key missing (legacy records)
            val = record.get(field) or record.get(field.lower(), "")
            row[field] = val if val else ""
        else:
            row[field] = _first(record, _LEGACY_KEYS[field])
    return row


def load_jobs(path: Path) -> list[dict[str, Any]]:
    """Read either the structured output or the original legacy JSON dump."""
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        jobs = payload.get("jobs")
        if isinstance(jobs, list):
            return [item for item in jobs if isinstance(item, dict)]
    return []


def write_json(result: ScrapeResult, runs_dir: Path, latest_dir: Path) -> Path:
    """Write run JSON to runs_dir and identical copy to latest_dir."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "query": result.params.query or "(all jobs)",
            "locations": list(result.params.locations),
            "pages_fetched": result.pages,
            "stopped_reason": ", ".join(
                f"{report.location}: {report.stopped_reason}" for report in result.reports
            ),
            "per_location": [
                {
                    "location": report.location,
                    "pages": report.pages,
                    "new_jobs": report.found,
                    "stopped_reason": report.stopped_reason,
                }
                for report in result.reports
            ],
            "total_jobs": len(result.jobs),
            "scraped_at": result.scraped_at.isoformat(),
            "session_id": result.session.id,
            "generator": "indeed_scraper",
            "fingerprint_version": 1,
        },
        "jobs": [
            {**job.model_dump(), "fingerprint": job_fingerprint(job), "short_id": short_id(job_fingerprint(job))}
            for job in result.jobs
        ],
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = runs_dir / f"jobs_{stamp}.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    (latest_dir / "jobs_latest.json").write_text(text, encoding="utf-8")
    return path


def records_to_csv(records: Sequence[Mapping[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS))
        writer.writeheader()
        for record in records:
            writer.writerow(normalize_record(record))
    return path


def jobs_to_csv(jobs: Sequence[Job], path: Path) -> Path:
    """Write one run's jobs to CSV, including their content fingerprints.

    The fingerprint is derived here rather than read from the record: a Job
    model carries no fingerprint field, so the "Job ID" and "Fingerprint"
    columns would otherwise always be blank.
    """
    dicts: list[dict[str, Any]] = []
    for job in jobs:
        fingerprint = job_fingerprint(job)
        dicts.append(
            {
                **job.model_dump(),
                "Job ID": short_id(fingerprint),
                "Fingerprint": fingerprint,
            }
        )
    return records_to_csv(dicts, path)
