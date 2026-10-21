"""Organize/replay run files into a master deduped job set.

Core is a PURE REPLAY over run files — no separate ledger file; runs
are the source of truth, master is derived and idempotently regenerable.
"""

from __future__ import annotations

from rich.console import Console

from indeed_scraper.config import Config
from indeed_scraper.organize.present import print_master
from indeed_scraper.organize.replay import replay, scan_runs, write_master


def organize_outputs(config: Config, console: Console) -> dict:
    """Full organize pipeline: scan runs -> replay -> write master -> print.

    Returns a summary dict with key counts.
    """
    run_files = scan_runs(config.runs_dir)
    if not run_files:
        console.print("[yellow]No run files found in data/runs.[/yellow]")
        return {"runs_ingested": 0, "unique_jobs": 0, "duplicate_postings": 0}

    result = replay(run_files)

    master_dir = config.master_dir
    master_dir.mkdir(parents=True, exist_ok=True)
    write_master(result, master_dir)

    print_master(result, console)

    return {
        "runs_ingested": len(run_files),
        "unique_jobs": len(result),
        "duplicate_postings": sum(1 for s in result.values() if s.get("duplicate_of", "") != ""),
    }


__all__ = ["organize_outputs", "print_master", "replay", "scan_runs", "write_master"]