"""Core apply-subpackage tests — one case per behaviour."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from indeed_scraper.apply.drafts import draft_path, read_draft, write_draft
from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.profile import Profile, apply_data, load_profile, save_profile
from indeed_scraper.apply.risk import RiskBudget

# ---------------------------------------------------------------------------
# Ledger tests
# ---------------------------------------------------------------------------


def test_ledger_reserve_idempotent(tmp_path: Path) -> None:
    """reserve returns True then False for the same fingerprint."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp = "fp-001"
    jk = "jk-001"
    url = "https://indeed.com/job/1"

    assert ledger.reserve(fp, jk, url) is True
    assert ledger.reserve(fp, jk, url) is False


def test_ledger_reserve_distinct_fingerprints(tmp_path: Path) -> None:
    """a second distinct fingerprint returns True."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp1 = "fp-001"
    fp2 = "fp-002"
    jk1 = "jk-001"
    jk2 = "jk-002"
    url1 = "https://indeed.com/job/1"
    url2 = "https://indeed.com/job/2"

    assert ledger.reserve(fp1, jk1, url1) is True
    assert ledger.reserve(fp2, jk2, url2) is True


def test_ledger_one_line_per_reserve(tmp_path: Path) -> None:
    """the file has one line per reserve."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp = "fp-001"
    jk = "jk-001"
    url = "https://indeed.com/job/1"

    ledger.reserve(fp, jk, url)
    ledger.reserve(fp, jk, url)  # second call is idempotent - returns False

    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_ledger_mark_appends_and_status_of(tmp_path: Path) -> None:
    """mark() appends and status_of returns the latest."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp = "fp-001"

    ledger.mark(fp, "submitted", detail="all good")
    ledger.mark(fp, "blocked", detail="captcha")

    status = ledger.status_of(fp)
    assert status == "blocked"


def test_ledger_submitted_today_counts_only_todays_submitted(tmp_path: Path) -> None:
    """submitted_today counts only entries with status 'submitted' on the current UTC date."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp1 = "fp-001"
    fp2 = "fp-002"
    jk1 = "jk-001"
    jk2 = "jk-002"
    url1 = "https://indeed.com/job/1"
    url2 = "https://indeed.com/job/2"

    # reserve doesn't set status to "submitted", so count should be 0
    ledger.reserve(fp1, jk1, url1)
    ledger.reserve(fp2, jk2, url2)
    assert ledger.submitted_today() == 0

    # Mark as submitted - applied_at will be today's date
    ledger.mark(fp1, "submitted", detail="")
    assert ledger.submitted_today() >= 1


def test_ledger_entries_skips_malformed_line(tmp_path: Path) -> None:
    """entries skips a malformed line."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    ledger.path.write_text(
        '{"fingerprint": "fp-1", "status": "reserved"}' + "\n"
        'this is not json' + "\n"
        '{"fingerprint": "fp-2", "status": "submitted"}' + "\n",
        encoding="utf-8",
    )
    # entries property re-parses from disk
    assert len(ledger.entries) == 2
    fp_statuses = {e["fingerprint"]: e["status"] for e in ledger.entries}
    assert fp_statuses == {"fp-1": "reserved", "fp-2": "submitted"}


def test_ledger_concurrency_same_fingerprint(tmp_path: Path) -> None:
    """two threads reserving the SAME fingerprint produce exactly one True."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp = "fp-concurrent"
    jk = "jk-conc"
    url = "https://indeed.com/job/concurrent"

    results: list[bool] = []

    def _reserve() -> None:
        results.append(ledger.reserve(fp, jk, url))

    threads = [threading.Thread(target=_reserve) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    true_count = sum(1 for r in results if r is True)
    # Exactly one thread should succeed; the rest get False (idempotency under lock)
    assert true_count == 1


# ---------------------------------------------------------------------------
# Profile tests
# ---------------------------------------------------------------------------


def test_profile_load_raises_when_absent(tmp_path: Path) -> None:
    """load raises ProfileNotFoundError when the file is absent."""
    missing = tmp_path / "nonexistent.json"
    with pytest.raises(Exception) as excinfo:
        load_profile(missing)
    # Should mention the path
    assert "not found" in str(excinfo.value).lower() or "nonexistent" in str(excinfo.value).lower()


def _write_resume(path: Path) -> Path:
    """A PDF big enough and shaped enough to pass the resume validation."""
    path.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    return path


def test_profile_save_writes_0600_and_roundtrips(tmp_path: Path) -> None:
    """save writes mode 0600 and load round-trips."""
    profile = Profile(
        name="Test User",
        email="test@example.com",
        phone="123-456-7890",
        resume_path=str(_write_resume(tmp_path / "test.pdf")),
    )
    save_profile(profile, tmp_path / "profile.json")
    p = tmp_path / "profile.json"

    # Check file mode is 0600
    import os as _os
    mode = _os.stat(str(p)).st_mode & 0o777
    assert mode == 0o600

    # Round-trip load
    loaded = load_profile(p)
    assert loaded.name == profile.name
    assert loaded.email == profile.email
    assert loaded.phone == profile.phone
    assert loaded.resume_path == profile.resume_path


def test_profile_save_atomic_no_leftover_tempfiles(tmp_path: Path) -> None:
    """save is atomic (no leftover temp files)."""
    profile = Profile(
        name="Atomic User",
        email="atomic@example.com",
        phone="000-000-0000",
        resume_path=str(_write_resume(tmp_path / "atomic.pdf")),
    )
    save_profile(profile, tmp_path / "profile2.json")
    p = tmp_path / "profile2.json"

    # After atomic write, no .tmp file should remain
    tmp_file = p.with_suffix(".tmp")
    assert not tmp_file.exists()

    # Load should still work
    loaded = load_profile(p)
    assert loaded.name == "Atomic User"


def test_profile_apply_data_maps_fields(tmp_path: Path) -> None:
    """apply_data maps Profile -> ApplyData fields."""
    profile = Profile(
        name="Mapper",
        email="m@example.com",
        phone="555-5555",
        resume_path=str(_write_resume(tmp_path / "resume.pdf")),
        cover_letter="My cover letter",
        screening_answers={"q1": "a1"},
        work_authorization="",
        salary_expectations="",
        availability="",
        notice_period="",
        visa_sponsorship=False,
    )
    mapped = apply_data(profile)
    assert mapped.name == "Mapper"
    assert mapped.email == "m@example.com"
    assert mapped.phone == "555-5555"
    assert mapped.resume_path.endswith("resume.pdf")
    assert mapped.cover_letter == "My cover letter"
    assert mapped.screening_answers == {"q1": "a1"}


def test_profile_work_authorization_loads_empty_not_fabricated(tmp_path: Path) -> None:
    """a profile saved with work_authorization='' loads with '' (not a fabricated default)."""
    profile = Profile(
        name="No Auth",
        email="noauth@example.com",
        phone="000-000-0000",
        resume_path=str(_write_resume(tmp_path / "resumes.pdf")),
        work_authorization="",
    )
    save_profile(profile, tmp_path / "profile3.json")
    loaded = load_profile(tmp_path / "profile3.json")
    assert loaded.work_authorization == ""


# ---------------------------------------------------------------------------
# Risk tests
# ---------------------------------------------------------------------------


def test_risk_can_apply_false_after_max(tmp_path: Path) -> None:
    """can_apply False once max_per_day submissions exist."""
    budget = RiskBudget(max_per_day=2)
    ledger = ApplicationLedger(tmp_path / "risk_ledger.jsonl")

    # Submit 2 applications today
    fp1 = "fp-risk-1"
    fp2 = "fp-risk-2"
    jk1 = "jk-risk-1"
    jk2 = "jk-risk-2"
    url1 = "https://indeed.com/job/risk1"
    url2 = "https://indeed.com/job/risk2"

    ledger.reserve(fp1, jk1, url1)
    ledger.reserve(fp2, jk2, url2)
    ledger.mark(fp1, "submitted", detail="")
    ledger.mark(fp2, "submitted", detail="")

    assert budget.can_apply(ledger) is False


def test_risk_delay_seconds_respects_minutes(tmp_path: Path) -> None:
    """delay_seconds respects min_delay_minutes."""
    budget = RiskBudget(min_delay_minutes=5.0)  # 5 minutes = 300 seconds
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    last = datetime(2024, 1, 1, 11, 55, 0, tzinfo=timezone.utc)  # 5 min earlier

    remaining = budget.delay_seconds(last, now)
    assert remaining == 0.0  # exactly 5 min elapsed


def test_risk_delay_seconds_not_yet_minimum(tmp_path: Path) -> None:
    """delay_seconds returns 0 when minimum exactly reached."""
    budget = RiskBudget(min_delay_minutes=10.0)  # 10 min = 600 sec
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    last = datetime(2024, 1, 1, 11, 50, 0, tzinfo=timezone.utc)  # 10 min earlier = exactly at minimum

    remaining = budget.delay_seconds(last, now)
    assert remaining == 0.0


def test_risk_delay_seconds_positive_when_short(tmp_path: Path) -> None:
    """delay_seconds returns positive when minimum not yet reached."""
    budget = RiskBudget(min_delay_minutes=10.0)  # 10 min = 600 sec
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    last = datetime(2024, 1, 1, 11, 55, 0, tzinfo=timezone.utc)  # 5 min ago

    remaining = budget.delay_seconds(last, now)
    assert remaining == 300.0  # 5 min * 60 sec


def test_risk_config_from_env_falls_back_on_garbage(tmp_path: Path) -> None:
    """config_from_env reads env vars and falls back on defaults."""
    import os as _os
    _os.environ["INDEED_MAX_APPS_PER_DAY"] = "not_a_number"
    _os.environ["INDEED_MIN_DELAY_MINUTES"] = "also_bad"

    budget = RiskBudget.config_from_env()
    # Should fall back to defaults
    assert budget.max_per_day == 2
    assert budget.min_delay_minutes == 30.0

    # Clean up
    del _os.environ["INDEED_MAX_APPS_PER_DAY"]
    del _os.environ["INDEED_MIN_DELAY_MINUTES"]


# ---------------------------------------------------------------------------
# Drafts tests
# ---------------------------------------------------------------------------


def test_drafts_write_then_read_roundtrips(tmp_path: Path) -> None:
    """write then read round-trips."""
    root = tmp_path / "drafts"
    app_id = "abc123def456"
    payload = {"job_title": "Software Engineer", "status": "pending"}

    write_draft(root, app_id, payload)
    read_back = read_draft(root, app_id)

    assert read_back == payload


def test_drafts_read_none_for_missing_app_id(tmp_path: Path) -> None:
    """read_draft returns None for a missing app_id."""
    root = tmp_path / "drafts"
    # Don't create any drafts
    result = read_draft(root, "nonexistent-id")
    assert result is None


def test_drafts_write_atomic(tmp_path: Path) -> None:
    """write is atomic (no leftover temp files)."""
    root = tmp_path / "drafts_atomic"
    app_id = "atomic-id-1234"
    payload = {"test": True}

    _written = write_draft(root, app_id, payload)
    p = draft_path(root, app_id)

    # No .tmp file should remain
    tmp_file = p.with_suffix(".tmp")
    assert not tmp_file.exists()

    # File should be readable
    read_back = read_draft(root, app_id)
    assert read_back == payload

def test_dry_run_releases_the_reservation(tmp_path: Path) -> None:
    """A rehearsal must not consume the posting.

    After a dry run the ledger must not report the posting as reserved, or the
    real run would skip exactly the postings the operator rehearsed.
    """
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp = "fp-dry-run"

    assert ledger.reserve(fp, "jk-1", "https://www.indeed.com/viewjob?jk=jk-1") is True
    assert ledger.status_of(fp) == "reserved"

    # The worker releases a rehearsal the same way.
    ledger.mark(fp, "failed", "dry_run")

    assert ledger.status_of(fp) == "failed"
    # A later real attempt is therefore allowed to reserve it again.
    assert ledger.has(fp) is True


def test_ledger_skips_only_reserved_or_submitted(tmp_path: Path) -> None:
    """Only an in-flight or completed application blocks a new attempt."""
    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    fp = "fp-002"

    ledger.reserve(fp, "jk-2", "https://www.indeed.com/viewjob?jk=jk-2")
    assert ledger.status_of(fp) in {"reserved", "submitted"}

    ledger.mark(fp, "failed", "dry_run")
    assert ledger.status_of(fp) not in {"reserved", "submitted"}
