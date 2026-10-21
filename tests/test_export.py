"""JSON/CSV export and legacy-format compatibility."""

from __future__ import annotations

import json
from pathlib import Path

from indeed_scraper.export import CSV_FIELDS, jobs_to_csv, load_jobs, normalize_record
from indeed_scraper.scraper import Job


def test_jobs_to_csv_writes_all_columns(tmp_path: Path) -> None:
    job = Job(
        jk="abc123",
        title="Data Engineer",
        company="Acme",
        location="Chicago, IL",
        salary="$100,000 a year",
        posted="3 days ago",
        snippet="Build pipelines",
        url="https://www.indeed.com/viewjob?jk=abc123",
    )
    path = jobs_to_csv([job], tmp_path / "jobs.csv")
    header, row = path.read_text(encoding="utf-8").splitlines()[:2]
    assert header.split(",") == list(CSV_FIELDS)
    assert "Data Engineer" in row
    assert "abc123" in row


def test_normalize_record_accepts_legacy_keys() -> None:
    record = {
        "Title": "Legacy",
        "Company": "OldCo",
        "Location": "Remote",
        "JobLink": "https://example.com",
        "Job Number": "42",
    }
    row = normalize_record(record)
    assert row["Title"] == "Legacy"
    assert row["Job Key"] == "42"
    assert row["Salary"] == ""


def test_load_jobs_handles_structured_and_legacy(tmp_path: Path) -> None:
    structured = tmp_path / "jobs.json"
    structured.write_text(json.dumps({"jobs": [{"jk": "1", "title": "A"}]}), encoding="utf-8")
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps([{"Text": "A\nB", "Tag": "div"}]), encoding="utf-8")

    assert load_jobs(structured)[0]["jk"] == "1"
    assert load_jobs(legacy)[0]["Tag"] == "div"
