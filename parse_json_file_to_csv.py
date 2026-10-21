#!/usr/bin/env python3
"""Convert a scraper JSON dump into a CSV file.

Defaults to the newest JSON in the state runs directory; pass a path to
convert a specific file. Handles both the structured format written today and
the legacy list-of-Text-blocks format from the Selenium era.
"""

from __future__ import annotations

import sys
from pathlib import Path

from indeed_scraper.config import Config
from indeed_scraper.export import load_jobs, records_to_csv


def find_input() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    config = Config.load()
    candidates = sorted(
        [
            *config.runs_dir.glob("jobs_*.json"),
            *config.latest_dir.glob("jobs_*.json"),
            *Path.cwd().glob("log_*.json"),
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit("No JSON file found; pass one explicitly.")
    return candidates[0]


def main() -> int:
    source = find_input()
    records = load_jobs(source)
    destination = source.with_name("job_data_extended.csv")
    records_to_csv(records, destination)
    print(f"Wrote {len(records)} rows from {source} to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
