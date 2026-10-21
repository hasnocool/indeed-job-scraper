"""Tests for the organize/replay pipeline (organize.py)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from indeed_scraper.config import Config
from indeed_scraper.organize import organize_outputs, replay, scan_runs, write_master


def _write_run_file(path: Path, jobs: list[dict], scraped_at: str, query: str = "test") -> None:
    """Write a run file in the expected format."""
    payload = {
        "meta": {
            "query": query,
            "locations": ["Test, BC"],
            "pages_fetched": 1,
            "stopped_reason": "max_pages",
            "total_jobs": len(jobs),
            "scraped_at": scraped_at,
            "session_id": "test-session",
            "generator": "indeed_scraper",
        },
        "jobs": jobs,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _make_job_dict(jk: str, **overrides) -> dict:
    base = {
        "jk": jk,
        "title": "Test Job",
        "company": "Test Co",
        "location": "Test, BC",
        "salary": "$50,000",
        "schedule": "Full-time",
        "posted": "3 days ago",
        "snippet": "test snippet",
        "url": f"https://indeed.com/viewjob?jk={jk}",
        "matches": ["Test, BC"],
    }
    base.update(overrides)
    return base


def test_scan_runs_excludes_latest_and_master(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    # Create valid run files
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [], "2026-10-20T10:00:00+00:00")
    _write_run_file(runs_dir / "jobs_20261020-110000.json", [], "2026-10-20T11:00:00+00:00")
    
    # Create files to exclude
    (runs_dir / "jobs_latest.json").write_text("{}")
    (runs_dir / "jobs_master.json").write_text("{}")
    (runs_dir / "jobs_master.csv").write_text("")
    
    runs = scan_runs(runs_dir)
    assert len(runs) == 2
    assert runs[0].name == "jobs_20261020-100000.json"
    assert runs[1].name == "jobs_20261020-110000.json"


def test_scan_runs_empty_dir(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    assert scan_runs(runs_dir) == []


def test_replay_same_jk_different_field_fullness(tmp_path: Path) -> None:
    """Same jk in both runs with different field fullness -> merged fullest, seen_count 2."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    # Run 1: minimal fields
    job1 = _make_job_dict("jk1", title="Engineer", company="", salary="")
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [job1], "2026-10-20T10:00:00+00:00")
    
    # Run 2: fuller fields
    job2 = _make_job_dict("jk1", title="Senior Engineer", company="Acme", salary="$100,000")
    _write_run_file(runs_dir / "jobs_20261020-110000.json", [job2], "2026-10-20T11:00:00+00:00")
    
    runs = scan_runs(runs_dir)
    result = replay(runs)
    
    assert "jk1" in result
    state = result["jk1"]
    assert state["seen_count"] == 2
    assert state["job"].title == "Senior Engineer"  # fuller wins
    assert state["job"].company == "Acme"
    assert state["job"].salary == "$100,000"
    # first_seen from run 1, last_seen from run 2
    assert state["first_seen"] == datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    assert state["last_seen"] == datetime(2026, 10, 20, 11, 0, 0, tzinfo=timezone.utc)


def test_replay_jk_only_in_latest_run(tmp_path: Path) -> None:
    """jk only in run 2 -> status 'new'."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    job1 = _make_job_dict("jk1")
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [job1], "2026-10-20T10:00:00+00:00")
    
    job2 = _make_job_dict("jk2")
    _write_run_file(runs_dir / "jobs_20261020-110000.json", [job2], "2026-10-20T11:00:00+00:00")
    
    runs = scan_runs(runs_dir)
    result = replay(runs)
    
    assert result["jk1"]["status"] == "new"
    assert result["jk2"]["status"] == "new"


def test_replay_jk_changed_salary_status_updated(tmp_path: Path) -> None:
    """jk in both with changed salary -> status 'updated'."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    job1 = _make_job_dict("jk1", salary="$50,000")
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [job1], "2026-10-20T10:00:00+00:00")
    
    job2 = _make_job_dict("jk1", salary="$60,000")
    _write_run_file(runs_dir / "jobs_20261020-110000.json", [job2], "2026-10-20T11:00:00+00:00")
    
    runs = scan_runs(runs_dir)
    result = replay(runs)
    
    assert result["jk1"]["status"] == "updated"


def test_replay_duplicate_of_same_content_different_jk(tmp_path: Path) -> None:
    """Same content under two different jks -> duplicate_of on the later one."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    # Same content, different jk - first run
    job1 = _make_job_dict("jk_original", title="Engineer", company="Acme")
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [job1], "2026-10-20T10:00:00+00:00")
    
    # Same content, different jk - second run
    job2 = _make_job_dict("jk_repost", title="Engineer", company="Acme")
    _write_run_file(runs_dir / "jobs_20261020-110000.json", [job2], "2026-10-20T11:00:00+00:00")
    
    runs = scan_runs(runs_dir)
    result = replay(runs)
    
    # The one with earliest first_seen (jk_original) should be original
    assert result["jk_original"]["duplicate_of"] == ""
    assert result["jk_repost"]["duplicate_of"] == "jk_original"


def test_write_master_writes_json_and_csv(tmp_path: Path) -> None:
    """master JSON + CSV written with expected columns/fields."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    job1 = _make_job_dict("jk1", title="Job A", company="Alpha Co")
    job2 = _make_job_dict("jk2", title="Job B", company="Beta Co")
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [job1, job2], "2026-10-20T10:00:00+00:00")
    
    runs = scan_runs(runs_dir)
    result = replay(runs)
    
    master_dir = tmp_path / "master"
    master_dir.mkdir()
    write_master(result, master_dir)
    
    # Check JSON
    master_json = master_dir / "jobs_master.json"
    assert master_json.exists()
    data = json.loads(master_json.read_text())
    assert "meta" in data
    assert "jobs" in data
    assert data["meta"]["total_jobs"] == 2
    assert data["meta"]["fingerprint_version"] == 1
    assert data["meta"]["fingerprint_fields"] == ["title", "company", "location", "salary", "schedule"]
    
    # Check CSV
    master_csv = master_dir / "jobs_master.csv"
    assert master_csv.exists()
    lines = master_csv.read_text(encoding="utf-8").splitlines()
    header = lines[0]
    # Check new columns present
    assert "Job ID" in header
    assert "Fingerprint" in header
    assert "Status" in header
    assert "First Seen" in header
    assert "Last Seen" in header
    assert "Seen Count" in header
    assert "Duplicate Of" in header
    
    # Check jobs sorted by (company, title, location)
    assert "Alpha Co" in lines[1]
    assert "Beta Co" in lines[2]


def test_jobs_latest_json_excluded_from_scan(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [], "2026-10-20T10:00:00+00:00")
    (runs_dir / "jobs_latest.json").write_text(json.dumps({"meta": {}, "jobs": [{"jk": "new", "title": "New"}]}))
    
    runs = scan_runs(runs_dir)
    assert len(runs) == 1
    assert runs[0].name == "jobs_20261020-100000.json"


def test_empty_runs_dir_writes_nothing(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    master_dir = tmp_path / "master"
    master_dir.mkdir()
    
    runs = scan_runs(runs_dir)
    assert runs == []
    
    # replay on empty returns empty
    result = replay(runs)
    assert result == {}
    
    # write_master should not crash and should create files (empty)
    write_master(result, master_dir)
    master_json = master_dir / "jobs_master.json"
    master_csv = master_dir / "jobs_master.csv"
    assert master_json.exists()
    assert master_csv.exists()
    
    data = json.loads(master_json.read_text())
    assert data["meta"]["total_jobs"] == 0


def test_master_sorted_by_company_title_location(tmp_path: Path) -> None:
    """Jobs in master sorted by (company, title, location)."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    # Intentionally out of order
    job1 = _make_job_dict("jk1", title="Zebra", company="Zeta")
    job2 = _make_job_dict("jk2", title="Alpha", company="Alpha")
    job3 = _make_job_dict("jk3", title="Beta", company="Alpha")
    _write_run_file(runs_dir / "jobs_20261020-100000.json", [job1, job2, job3], "2026-10-20T10:00:00+00:00")
    
    runs = scan_runs(runs_dir)
    result = replay(runs)
    
    master_dir = tmp_path / "master"
    master_dir.mkdir()
    write_master(result, master_dir)
    
    master_json = master_dir / "jobs_master.json"
    data = json.loads(master_json.read_text())
    jobs = data["jobs"]
    
    # Should be sorted: Alpha/Alpha, Alpha/Beta, Zeta/Zebra
    assert jobs[0]["company"] == "Alpha"
    assert jobs[0]["title"] == "Alpha"
    assert jobs[1]["company"] == "Alpha"
    assert jobs[1]["title"] == "Beta"
    assert jobs[2]["company"] == "Zeta"
    assert jobs[2]["title"] == "Zebra"


def test_organize_outputs_no_run_files(tmp_path: Path) -> None:
    """organize_outputs with empty runs_dir returns early without writing."""
    config = Config.load(state_dir=tmp_path / "data")
    config.ensure_dirs()
    
    from rich.console import Console
    console = Console()
    
    result = organize_outputs(config, console)
    assert result["runs_ingested"] == 0
    assert result["unique_jobs"] == 0
    
    # master_dir should not be created (or should be empty)
    master_dir = config.master_dir
    if master_dir.exists():
        # The function creates the dir but doesn't write files
        assert not (master_dir / "jobs_master.json").exists()