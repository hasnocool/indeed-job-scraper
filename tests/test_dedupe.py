"""Tests for hash-based job deduplication (dedupe.py)."""

from __future__ import annotations

import json

from indeed_scraper.dedupe import FINGERPRINT_FIELDS, job_fingerprint, short_id
from indeed_scraper.scraper import Job


def _make_job(**overrides) -> Job:
    base = {
        "jk": "abc123",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "salary": "$150,000/year",
        "schedule": "Full-time",
        "posted": "3 days ago",
        "snippet": "Build cool stuff",
        "url": "https://indeed.com/viewjob?jk=abc123",
    }
    base.update(overrides)
    return Job(**base)


def test_fingerprint_fields() -> None:
    assert FINGERPRINT_FIELDS == ("title", "company", "location", "salary", "schedule")


def test_fingerprint_determinism() -> None:
    """Same content -> same hash."""
    job1 = _make_job()
    job2 = _make_job()
    assert job_fingerprint(job1) == job_fingerprint(job2)
    assert short_id(job_fingerprint(job1)) == short_id(job_fingerprint(job2))


def test_fingerprint_sensitivity_to_content_change() -> None:
    """Changing a fingerprint field changes the hash."""
    job1 = _make_job()
    job2 = _make_job(title="Senior Software Engineer")
    assert job_fingerprint(job1) != job_fingerprint(job2)

    job3 = _make_job(salary="$200,000/year")
    assert job_fingerprint(job1) != job_fingerprint(job3)


def test_fingerprint_excludes_volatile_fields() -> None:
    """Changes to excluded fields do NOT change the hash."""
    base = _make_job()
    
    # Change posted (relative age drifts run-to-run)
    assert job_fingerprint(base) == job_fingerprint(_make_job(posted="1 hour ago"))
    
    # Change snippet (truncation varies)
    assert job_fingerprint(base) == job_fingerprint(_make_job(snippet="Different snippet text"))
    
    # Change jk (re-posted under new key should hash identically)
    assert job_fingerprint(base) == job_fingerprint(_make_job(jk="new_key_999"))
    
    # Change url (derives from jk)
    assert job_fingerprint(base) == job_fingerprint(_make_job(url="https://indeed.com/viewjob?jk=new_key_999"))
    
    # Change matches (per-run context)
    assert job_fingerprint(base) == job_fingerprint(_make_job(matches=("Loc1", "Loc2")))


def test_short_id_prefix() -> None:
    """short_id returns first 12 hex chars of fingerprint."""
    job = _make_job()
    fp = job_fingerprint(job)
    sid = short_id(fp)
    assert sid == fp[:12]
    assert len(sid) == 12


def test_fingerprint_canonical_json_format() -> None:
    """Fingerprint uses canonical JSON: sorted keys, no whitespace, ensure_ascii=False."""
    job = _make_job(title="Test", company="Co", location="Loc", salary="", schedule="")
    fp = job_fingerprint(job)
    
    # Manually compute expected
    canonical = json.dumps(
        {"company": "Co", "location": "Loc", "salary": "", "schedule": "", "title": "Test"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    import hashlib
    expected = hashlib.sha256(canonical).hexdigest()
    assert fp == expected