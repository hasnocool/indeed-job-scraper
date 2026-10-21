"""Tests for indeed_scraper.response_monitor."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from indeed_scraper.response_monitor import (
    app_id_for,
    collect_responses,
    list_responses,
    parse_status,
    read_response,
    write_response,
)


class TestAppIdFor:
    def test_returns_12_char_prefix(self):
        fingerprint = "a" * 20
        result = app_id_for(fingerprint)
        assert result == "a" * 12


class TestParseStatus:
    def test_interview_scheduled(self):
        assert parse_status("Interview scheduled") == "interview"

    def test_application_viewed(self):
        assert parse_status("Application viewed") == "viewed"

    def test_rejected(self):
        assert parse_status("We have decided not to move forward") == "rejected"

    def test_empty_string(self):
        assert parse_status("") == "unknown"

    def test_unknown_default(self):
        assert parse_status("some random text") == "unknown"


class TestWriteReadRoundtrip:
    def test_atomic_0600_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "responses"
            payload = {"app_id": "abc123def456", "status": "viewed"}
            path = write_response(root, "abc123def456", payload)
            # Check mode is 0600
            mode = oct(path.stat().st_mode & 0o777)
            assert mode == "0o600", f"Expected 0o600, got {mode}"
            # Round-trip read
            data = read_response(root, "abc123def456")
            assert data == payload

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "responses"
            data = read_response(root, "nonexistent")
            assert data is None


class TestListResponses:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "responses"
            root.mkdir(parents=True, exist_ok=True)
            records = list_responses(root)
            assert records == []

    def test_lists_valid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "responses"
            root.mkdir(parents=True, exist_ok=True)
            # Write two response files
            write_response(root, "app1", {"app_id": "app1", "status": "viewed"})
            write_response(root, "app2", {"app_id": "app2", "status": "interview"})
            records = list_responses(root)
            assert len(records) == 2


class TestCollectResponses:
    def test_missing_ledger_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "nonexistent_ledger.jsonl"
            responses_root = Path(tmp) / "responses"
            result = collect_responses(ledger, responses_root)
            assert result == []
            # Should write nothing
            assert not responses_root.is_dir() or len(list(responses_root.iterdir())) == 0

    def test_skips_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.jsonl"
            responses_root = Path(tmp) / "responses"
            ledger_path.write_text(
                '{"fingerprint": "fp1", "jk": "jk1", "status": "submitted", "company": "Acme", "title": "Eng1"}\n'
                'this is not json\n'
                '{"fingerprint": "fp2", "jk": "jk2", "status": "submitted", "company": "Beta", "title": "Eng2"}\n',
                encoding="utf-8",
            )
            result = collect_responses(ledger_path, responses_root)
            # Only the two valid entries with "submitted" status should be processed
            assert len(result) == 2
            companies = {r["company"] for r in result}
            assert "Acme" in companies
            assert "Beta" in companies

    def test_submitted_and_reserved_skips_reserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.jsonl"
            responses_root = Path(tmp) / "responses"
            ledger_path.write_text(
                json.dumps(
                    {
                        "fingerprint": "fp1",
                        "jk": "jk1",
                        "status": "submitted",
                        "company": "Acme",
                        "title": "Engineer",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            ledger_path.write_text(
                json.dumps(
                    {
                        "fingerprint": "fp2",
                        "jk": "jk2",
                        "status": "reserved",
                        "company": "Beta",
                        "title": "Designer",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            # Actually write both to same file
            combined = (
                json.dumps(
                    {
                        "fingerprint": "fp1",
                        "jk": "jk1",
                        "status": "submitted",
                        "company": "Acme",
                        "title": "Engineer",
                    }
               )
                + "\n"
                + json.dumps(
                    {
                        "fingerprint": "fp2",
                        "jk": "jk2",
                        "status": "reserved",
                        "company": "Beta",
                        "title": "Designer",
                    }
                )
                + "\n"
            )
            ledger_path.write_text(combined, encoding="utf-8")

            result = collect_responses(ledger_path, responses_root)
            # Only the "submitted" entry should produce a record
            assert len(result) == 1
            assert result[0]["company"] == "Acme"
            assert result[0]["title"] == "Engineer"
            assert result[0]["jk"] == "jk1"

    def test_injected_fetch_status_overrides_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.jsonl"
            responses_root = Path(tmp) / "responses"

            def fetch_status(jk: str) -> str | None:
                # Mock live Indeed status text
                if jk == "jk1":
                    return "Interview scheduled"
                return None

            ledger_path.write_text(
                json.dumps(
                    {
                        "fingerprint": "fp1",
                        "jk": "jk1",
                        "status": "submitted",
                        "company": "Acme",
                        "title": "Engineer",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = collect_responses(ledger_path, responses_root, fetch_status=fetch_status)
            assert len(result) == 1
            assert result[0]["status"] == "interview"
            # The record should reflect the fetched status
            assert result[0]["status"] == "interview"

    def test_writes_one_record_for_submitted_among_multiple(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.jsonl"
            responses_root = Path(tmp) / "responses"

            ledger_path.write_text(
                json.dumps(
                    {
                        "fingerprint": "fp1",
                        "jk": "jk1",
                        "status": "submitted",
                        "company": "Acme",
                        "title": "Engineer",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "fingerprint": "fp2",
                        "jk": "jk2",
                        "status": "reserved",
                        "company": "Beta",
                        "title": "Designer",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "fingerprint": "fp3",
                        "jk": "jk3",
                        "status": "submitted",
                        "company": "Gamma",
                        "title": "Analyst",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = collect_responses(ledger_path, responses_root)
            # Only submitted entries should produce records
            assert len(result) == 2  # fp1 and fp3
            companies = {r["company"] for r in result}
            assert "Acme" in companies
            assert "Gamma" in companies
            # Should have written two response files
            written = list(responses_root.glob("*.json"))
            assert len(written) == 2