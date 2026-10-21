"""Application ledger with JSONL storage and fcntl-based file locking.

The ledger is the idempotency guard: a posting is reserved here BEFORE the
browser is touched, so a crash or a second run can never apply to the same
posting twice.

Two properties matter and are enforced here:

* **Atomic reservation across processes.** The file is re-read *inside* the
  lock before the presence check, so a reservation made by another process
  between our read and our lock is still seen.
* **Append-only, atomic writes.** Every line is appended with a single
  ``O_APPEND`` write; the file is never rewritten, so a crash cannot truncate
  the history. The last line for a fingerprint carries its current status.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOCK_SUFFIX = ".lock"
FILE_MODE = 0o600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    # Internal helpers
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
            except json.JSONDecodeError:
                # A partially written line is skipped, not fatal.
                continue
            if isinstance(record, dict):
                self._entries.append(record)

    @contextmanager
    def _lock(self):
        """Hold an exclusive flock on the sibling lock file (0600)."""
        lock_path = self.path.with_suffix(LOCK_SUFFIX)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a", encoding="utf-8") as handle:
            try:
                os.chmod(lock_path, FILE_MODE)
            except OSError:
                pass
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _append_line(self, record: dict) -> None:
        """Append one JSON line with a single atomic O_APPEND write."""
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, FILE_MODE)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)

    def _has_fingerprint_unlocked(self, fingerprint: str) -> bool:
        """Check fingerprint presence in the CURRENT file contents.

        The caller holds the lock, so the file must be re-read here: the
        in-memory copy may predate a reservation made by another process.
        """
        self._reparse()
        return any(entry.get("fingerprint") == fingerprint for entry in self._entries)

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
        self._reparse()
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
        ``os.write`` with ``O_APPEND``. Returns ``False`` if the fingerprint
        already exists (idempotency). On success a line with status
        ``"reserved"`` is written containing:

        ``fingerprint``, ``jk``, ``indeed_url``, ``company``, ``title``,
        ``applied_at`` (ISO UTC), ``status``, ``detail``.
        """
        with self._lock():
            # Re-read under the lock: another process may have reserved this
            # fingerprint since we last looked.
            if self._has_fingerprint_unlocked(fingerprint):
                return False

            self._append_line(
                {
                    "fingerprint": fingerprint,
                    "jk": jk,
                    "indeed_url": indeed_url,
                    "company": company,
                    "title": title,
                    "applied_at": _now_iso(),
                    "status": "reserved",
                    "detail": "",
                }
            )
            self._reparse()
            return True

    def mark(self, fingerprint: str, status: str, detail: str = "") -> None:
        """Append a line recording the new status for a fingerprint.

        The ledger is append-only: this adds a new line and never rewrites the
        file, so a crash cannot truncate the history. The last line for a
        fingerprint carries its current status.

        The job metadata (``jk``, ``indeed_url``, ``company``, ``title``) is
        carried forward from the reservation, so a consumer reading only the
        latest line still knows which posting the status refers to.
        """
        with self._lock():
            record = self._metadata_for(fingerprint)
            record.update(
                {
                    "fingerprint": fingerprint,
                    "status": status,
                    "detail": detail,
                    "applied_at": _now_iso(),
                }
            )
            self._append_line(record)
            self._reparse()

    def _metadata_for(self, fingerprint: str) -> dict:
        """The job metadata known for a fingerprint (from its reservation)."""
        self._reparse()
        known: dict = {}
        for entry in self._entries:
            if entry.get("fingerprint") != fingerprint:
                continue
            for key in ("jk", "indeed_url", "company", "title"):
                value = entry.get(key)
                if value:
                    known[key] = value
        return known

    def status_of(self, fingerprint: str) -> str | None:
        """Return the latest status recorded for a fingerprint."""
        self._reparse()
        latest: str | None = None
        for entry in self._entries:
            if entry.get("fingerprint") == fingerprint:
                status = entry.get("status")
                if isinstance(status, str):
                    latest = status
        return latest

    def submitted_today(self, now: datetime | None = None) -> int:
        """Count the postings submitted today.

        Each fingerprint counts once, using its LATEST status, so a posting
        that was marked more than once cannot inflate the count and wrongly
        block the operator's daily budget.
        """
        self._reparse()
        moment = now or datetime.now(timezone.utc)
        today = moment.date()

        latest: dict[str, dict] = {}
        for entry in self._entries:
            fingerprint = entry.get("fingerprint")
            if isinstance(fingerprint, str):
                latest[fingerprint] = entry

        count = 0
        for entry in latest.values():
            if entry.get("status") != "submitted":
                continue
            stamp = entry.get("applied_at")
            if not isinstance(stamp, str):
                continue
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when.date() == today:
                count += 1
        return count
