"""Application ledger with JSONL storage and fcntl-based file locking."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class ApplicationLedger:
    """JSONL-based ledger of job applications with fcntl locking.

    Each line is a JSON object with a ``fingerprint`` field.
    Locking is performed on a sibling ``.lock`` file using ``fcntl.flock``.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict] = []
        self._reparse()

    # ------------------------------------------------------------------
    # Internal re-parse of the JSONL file
    # ------------------------------------------------------------------

    def _reparse(self) -> None:
        """Re-read the JSONL file, skipping malformed lines."""
        self._entries = []
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                self._entries.append(record)
            except json.JSONDecodeError:
                # skip malformed lines silently
                continue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def entries(self) -> list[dict]:
        """Return the parsed entries (malformed lines are skipped), re-parsing from disk."""
        self._reparse()
        return self._entries

    def has(self, fingerprint: str) -> bool:
        """Return True if a fingerprint already exists in the ledger."""
        return any(entry.get("fingerprint") == fingerprint for entry in self._entries)

    def reserve(
        self,
        fingerprint: str,
        jk: str,
        indeed_url: str,
        company: str = "",
        title: str = "",
    ) -> bool:
        """Atomically reserve a fingerprint.

        Uses ``fcntl.flock`` on a sibling ``.lock`` file and a single
        ``os.write`` with ``O_APPEND``.  Returns ``False`` if the
        fingerprint already exists (idempotency).  On success a line
        with status ``"reserved```` is written containing:

        ``fingerprint``, ``jk``, ``indeed_url``, ``company``, ``title``,
        ``applied_at`` (ISO UTC), ``status``, ``detail``.
        """
        lock_path = self.path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with open(lock_path, "a", encoding="utf-8") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                # Check idempotency under lock
                if self._has_fingerprint_unlocked(fingerprint):
                    return False

                # Append the reserved line atomically via O_APPEND
                now_iso = datetime.now(timezone.utc).isoformat()
                record = {
                    "fingerprint": fingerprint,
                    "jk": jk,
                    "indeed_url": indeed_url,
                    "company": company,
                    "title": title,
                    "applied_at": now_iso,
                    "status": "reserved",
                    "detail": "",
                }
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

                fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
                try:
                    os.write(fd, line.encode("utf-8"))
                finally:
                    os.close(fd)

                # Refresh in-memory entries so callers see the new record
                self._reparse()
                return True
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)

    def _has_fingerprint_unlocked(self, fingerprint: str) -> bool:
        """Check fingerprint presence without re-parsing (caller holds lock)."""
        return any(entry.get("fingerprint") == fingerprint for entry in self._entries)

    def mark(self, fingerprint: str, status: str, detail: str = "") -> None:
        """Append an UPDATED line for the given fingerprint.

        Writes a new line containing the updated ``status`` and optional
        ``detail``.  The new line becomes the latest entry for that
        fingerprint.  If no existing entry has that fingerprint, a minimal
        record is still appended.
        """
        lock_path = self.path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with open(lock_path, "a", encoding="utf-8") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                # Re-read entries under lock
                self._reparse()
                # Append a new updated record
                now_iso = datetime.now(timezone.utc).isoformat()
                record = {
                    "fingerprint": fingerprint,
                    "status": status,
                    "detail": detail,
                    "applied_at": now_iso,
                }
                self._entries.append(record)
                # Write the entire ledger back
                self._write_entries()
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)

    def _write_entries(self) -> None:
        """Write the current in-memory entries back to the JSONL file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n" for entry in self._entries)

    def status_of(self, fingerprint: str) -> str | None:
        """Return the latest status for the given fingerprint, or None.

        Since entries are appended, the last matching entry is the latest.
        """
        for entry in reversed(self._entries):
            if entry.get("fingerprint") == fingerprint:
                return entry.get("status")
        return None

    def submitted_today(self, now: datetime | None = None) -> int:
        """Count entries with status ``"submitted```` on the current UTC date.

        ``now`` may be injected for testing; defaults to ``datetime.now(timezone.utc)``.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        today = now.date()
        count = 0
        for entry in self._entries:
            if entry.get("status") != "submitted":
                continue
            applied_at = entry.get("applied_at", "")
            try:
                entry_date = datetime.fromisoformat(applied_at).date()
            except (ValueError, TypeError):
                continue
            if entry_date == today:
                count += 1
        return count