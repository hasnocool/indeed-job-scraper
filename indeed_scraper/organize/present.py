"""Presentation helpers for organize output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table


def print_master(result: dict[str, dict], console: Console) -> None:
    """Print a rich Table summary of the organized result."""
    new_count = sum(1 for s in result.values() if s.get("status") == "new")
    updated_count = sum(1 for s in result.values() if s.get("status") == "updated")
    unchanged_count = sum(1 for s in result.values() if s.get("status") == "unchanged")
    duplicate_count = sum(1 for s in result.values() if s.get("duplicate_of", "") != "")

    all_run_files = set()
    for s in result.values():
        all_run_files.update(s["runs"])

    summary = Table(title="Indeed Job Deduplication Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="center")
    summary.add_row("Runs ingested", str(len(all_run_files)))
    summary.add_row("Unique jobs", str(len(result)))
    summary.add_row("Duplicate postings", str(duplicate_count))
    summary.add_row("New (first-time)", str(new_count))
    summary.add_row("Updated (changed content)", str(updated_count))
    summary.add_row("Unchanged (same content)", str(unchanged_count))

    console.print(summary)

    table = Table(title="Merged Jobs", show_header=True)
    table.add_column("Job ID", style="cyan", width=12)
    table.add_column("Company", style="green")
    table.add_column("Title", style="magenta")
    table.add_column("Location", style="yellow")
    table.add_column("Salary", style="blue")
    table.add_column("Posted", style="white")
    table.add_column("Status", style="red")

    for jk, state in sorted(result.items(), key=lambda x: (x[1]["job"].company, x[1]["job"].title)):
        job = state["job"]
        title = job.title or ""
        company = job.company or ""
        location = job.location or ""
        salary = job.salary or ""
        posted = job.posted or ""
        status = state.get("status", "unchanged")
        short = state.get("short_id", "")[:12]
        table.add_row(short, company, title, location, salary, posted, status)

    console.print(table)