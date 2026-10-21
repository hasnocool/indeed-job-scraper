"""Replay run files into a cross-run deduped job set."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from indeed_scraper.dedupe import job_fingerprint, short_id
from indeed_scraper.export import CSV_FIELDS, load_jobs
from indeed_scraper.scraper import Job

RUN_FILE_RE = re.compile(r"^jobs_(\d{8})-(\d{6})\.json$")


def scan_runs(runs_dir: Path) -> list[Path]:
    """Return run files matching ``jobs_YYYYMMDD-HHMMSS.json``, sorted
    chronologically by stamp.  Exclude ``jobs_latest*`` and
    ``jobs_master*``."""
    if not runs_dir.is_dir():
        return []
    files: list[Path] = []
    for p in runs_dir.iterdir():
        if p.name == "jobs_latest.json" or p.name.startswith("jobs_master"):
            continue
        m = RUN_FILE_RE.match(p.name)
        if m:
            files.append(p)
    files.sort(key=lambda p: p.name)
    return files


def _sighting_time(run_path: Path, meta: dict) -> datetime:
    """Return the sighting time for a run: use meta.scraped_at, or parse
    the filename stamp as fallback."""
    if meta and "scraped_at" in meta:
        try:
            return datetime.fromisoformat(meta["scraped_at"])
        except (ValueError, TypeError):
            pass
    m = RUN_FILE_RE.match(run_path.name)
    if m:
        dt_str = f"{m.group(1)}{m.group(2)}"
        return datetime.strptime(dt_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def replay(run_files: list[Path]) -> dict[str, dict]:
    """Replay run files and return a per-jk dict with merged data.

    Returns a dict keyed by jk with:
      - "job": merged Job
      - "first_seen": datetime (first run where jk appeared)
      - "last_seen": datetime (last run where jk appeared)
      - "seen_count": int (number of runs containing this jk)
      - "runs": list of run filenames (in chronological order)
      - "fingerprint": str (SHA-256 hexdigest)
      - "short_id": str (first 12 hex chars)
      - "status": {"new", "updated", "unchanged"}
      - "duplicate_of": str (original jk or "")
    """
    jk_state: dict[str, dict] = {}

    for run_path in run_files:
        payload = load_jobs(run_path)
        text = run_path.read_text(encoding="utf-8")
        raw = json.loads(text)
        meta = raw.get("meta", {}) if isinstance(raw, dict) else {}

        sighting = _sighting_time(run_path, meta)
        run_stamp = run_path.name

        for job_dict in payload:
            if not isinstance(job_dict, dict):
                continue
            jk = job_dict.get("jk")
            if not jk:
                continue

            job_model = Job(**job_dict)
            incoming_fp = job_fingerprint(job_model)
            incoming_sid = short_id(incoming_fp)

            if jk not in jk_state:
                jk_state[jk] = {
                    "job": job_model,
                    "first_seen": sighting,
                    "last_seen": sighting,
                    "seen_count": 1,
                    "runs": [run_stamp],
                    "fingerprint": incoming_fp,
                    "short_id": incoming_sid,
                    "status": "new",
                }
            else:
                state = jk_state[jk]
                existing_job = state["job"]
                updates: dict[str, str] = {}
                for field in ("title", "company", "location", "salary", "schedule", "posted", "snippet", "url"):
                    current = str(getattr(existing_job, field))
                    candidate = str(job_model.__getattribute__(field))
                    if len(candidate) > len(current):
                        updates[field] = candidate
                existing_matches = list(existing_job.matches)
                incoming_matches = list(job_model.matches)
                all_matches = existing_matches + [m for m in incoming_matches if m not in existing_matches]
                if all_matches != existing_matches:
                    updates["matches"] = tuple(all_matches)
                if updates:
                    existing_job = existing_job.model_copy(update=updates)
                state["job"] = existing_job

                state["last_seen"] = sighting
                state["seen_count"] += 1
                state["runs"].append(run_stamp)

                if incoming_fp != state["fingerprint"]:
                    state["fingerprint"] = incoming_fp
                    state["short_id"] = incoming_sid
                    state["status"] = "updated"
                else:
                    state["status"] = "unchanged"

    fingerprint_groups: dict[str, list[str]] = {}
    for jk, state in jk_state.items():
        fp = state["fingerprint"]
        fingerprint_groups.setdefault(fp, []).append(jk)

    duplicate_map: dict[str, str] = {}
    for fp, jks in fingerprint_groups.items():
        if len(jks) < 2:
            continue
        sorted_jks = sorted(jks, key=lambda j: (jk_state[j]["first_seen"], j))
        original_jk = sorted_jks[0]
        for jk in sorted_jks[1:]:
            duplicate_map[jk] = original_jk

    result: dict[str, dict] = {}
    for jk, state in jk_state.items():
        state = dict(state)
        state["duplicate_of"] = duplicate_map.get(jk, "")
        result[jk] = state

    return result


def write_master(result: dict[str, dict], master_dir: Path) -> None:
    """Write jobs_master.json and jobs_master.csv to master_dir.

    The JSON file contains meta + jobs list sorted by (company, title, location).
    The CSV file uses CSV_FIELDS (which already includes dedup columns).
    """
    new_count = sum(1 for s in result.values() if s.get("status") == "new")
    updated_count = sum(1 for s in result.values() if s.get("status") == "updated")
    unchanged_count = sum(1 for s in result.values() if s.get("status") == "unchanged")

    jobs_list = []
    for state in result.values():
        job = state["job"]
        job_dict = job.model_dump()
        job_dict["fingerprint"] = state["fingerprint"]
        job_dict["short_id"] = state["short_id"]
        job_dict["status"] = state.get("status", "unchanged")
        job_dict["first_seen"] = state["first_seen"].isoformat() if isinstance(state["first_seen"], datetime) else str(state["first_seen"])
        job_dict["last_seen"] = state["last_seen"].isoformat() if isinstance(state["last_seen"], datetime) else str(state["last_seen"])
        job_dict["seen_count"] = state["seen_count"]
        job_dict["duplicate_of"] = state.get("duplicate_of", "")
        jobs_list.append(job_dict)

    jobs_list.sort(key=lambda j: (j.get("company") or "", j.get("title") or "", j.get("location") or ""))

    all_runs = set()
    for state in result.values():
        all_runs.update(state["runs"])
    runs_ingested_sorted = sorted(all_runs)

    total_unique_jks = len(result)
    duplicate_postings = sum(1 for s in result.values() if s.get("duplicate_of", "") != "")

    meta = {
        "runs_ingested": runs_ingested_sorted,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint_version": 1,
        "fingerprint_fields": ["title", "company", "location", "salary", "schedule"],
        "total_jobs": total_unique_jks,
        "duplicate_postings": duplicate_postings,
        "status_counts": {
            "new": new_count,
            "updated": updated_count,
            "unchanged": unchanged_count,
        },
        "first_seen_across_all": min(
            (s["first_seen"] for s in result.values()),
            default=None,
        ),
        "last_seen_across_all": max(
            (s["last_seen"] for s in result.values()),
            default=None,
        ),
    }
    if meta["first_seen_across_all"] is not None:
        meta["first_seen_across_all"] = meta["first_seen_across_all"].isoformat()
    if meta["last_seen_across_all"] is not None:
        meta["last_seen_across_all"] = meta["last_seen_across_all"].isoformat()

    master_json = {"meta": meta, "jobs": jobs_list}
    master_json_path = master_dir / "jobs_master.json"
    text = json.dumps(master_json, indent=2, ensure_ascii=False) + "\n"
    master_json_path.write_text(text, encoding="utf-8")

    csv_path = master_dir / "jobs_master.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS))
        writer.writeheader()
        for job in jobs_list:
            row: dict[str, str] = {}
            for field in CSV_FIELDS:
                if field == "Matched Locations":
                    matches = job.get("matches")
                    if isinstance(matches, (list, tuple)):
                        row[field] = "; ".join(str(item) for item in matches)
                    else:
                        row[field] = str(matches or "")
                elif field in {"Job ID", "Fingerprint", "Status", "First Seen", "Last Seen", "Seen Count", "Duplicate Of"}:
                    key_map_new = {
                        "Job ID": "short_id",
                        "Fingerprint": "fingerprint",
                        "Status": "status",
                        "First Seen": "first_seen",
                        "Last Seen": "last_seen",
                        "Seen Count": "seen_count",
                        "Duplicate Of": "duplicate_of",
                    }
                    key = key_map_new.get(field, "")
                    if key and key in job:
                        row[field] = str(job[key])
                    else:
                        row[field] = ""
                else:
                    key_map = {
                        "Title": "title",
                        "Company": "company",
                        "Location": "location",
                        "Salary": "salary",
                        "Schedule": "schedule",
                        "Posted Date": "posted",
                        "Job Description": "snippet",
                        "JobLink": "url",
                        "Job Key": "jk",
                    }
                    key = key_map.get(field, "")
                    if key and key in job:
                        row[field] = str(job[key])
                    else:
                        row[field] = ""
            writer.writerow(row)