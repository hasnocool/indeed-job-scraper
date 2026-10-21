"""Workspace layout for the application flow.

Every path the flow writes to is derived here, so the data/ layout stays in
one place: the ledger, the per-application drafts and the response records.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..export import load_jobs
from ..scraper import Job

LEDGER_FILENAME = "ledger.jsonl"
DRAFTS_DIRNAME = "drafts"
RESULTS_FILENAME = "applications.csv"


def applications_dir(config: Config) -> Path:
    """The application data directory (created on demand)."""
    path = config.state_dir / "applications"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ledger_path(config: Config) -> Path:
    """The append-only application ledger."""
    return applications_dir(config) / LEDGER_FILENAME


def drafts_dir(config: Config) -> Path:
    """Root of the per-application draft directories."""
    path = applications_dir(config) / DRAFTS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def responses_dir(config: Config) -> Path:
    """Root of the recorded employer responses."""
    path = config.state_dir / "responses"
    path.mkdir(parents=True, exist_ok=True)
    return path


def results_path(config: Config) -> Path:
    """Where the outcome of a run is written."""
    return applications_dir(config) / RESULTS_FILENAME


def load_master_jobs(config: Config) -> list[Job]:
    """Read the organized master dataset as Job records."""
    path = config.master_dir / "jobs_master.json"
    if not path.is_file():
        return []
    jobs: list[Job] = []
    for record in load_jobs(path):
        if not isinstance(record, dict):
            continue
        fields = {k: v for k, v in record.items() if k in Job.model_fields}
        try:
            jobs.append(Job.model_validate(fields))
        except ValueError:
            continue
    return jobs
