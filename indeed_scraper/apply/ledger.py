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
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .budget_day import same_budget_day
from .ledger_recovery import (
    is_truncated_tail,
    latest_by_fingerprint,
    latest_status,
    metadata_for,
    parse_line,
    recover_torn_line,
    reservation_age,
)
from .status import normalise_text, strip_location_suffix

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
        """Re-read the JSONL file, recovering a torn final line.

        A malformed line in the MIDDLE of the file is skipped, but it is
        SURFACED with a warning - silently dropping a corrupted line hides a
        real problem with the file.

        A truncated FINAL line (no trailing newline - the file was cut off by
        a crash mid-append) is RECOVERED as a live reservation. The old
        behaviour dropped it, which silently un-reserved the posting and
        let the flow apply to it a second time. Recovering it keeps the
        posting blocked; the normal lease still expires it, so an abandoned
        run becomes retryable rather than locked out for ever.
        """
        self._entries = []
        if not self.path.exists():
            return
        text = self.path.read_text(encoding="utf-8")
        lines = text.splitlines()
        last_index = len(lines) - 1
        for idx, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue
            record = parse_line(line)
            if record is not None:
                self._entries.append(record)
                continue
            if idx - 1 == last_index and is_truncated_tail(text):
                recovered = recover_torn_line(line)
                if recovered is not None:
                    warnings.warn(
                        f"ledger {self.path}: the last line was truncated by a "
                        f"crash; recovered it as a live reservation for "
                        f"{recovered.get('fingerprint')!r}",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    self._entries.append(recovered)
                    continue
            warnings.warn(
                f"ledger {self.path}: malformed JSON at line {idx}",
                RuntimeWarning,
                stacklevel=2,
            )

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

    #: A posting in one of these states must not be applied to again. Every
    #: other status (failed, dry_run, declined, ...) is retryable: a run that
    #: was killed, or that the operator declined, must not lock the posting
    #: out for ever.
    LIVE_STATUSES = frozenset({"reserved", "submitting", "submitted", "unconfirmed"})

    #: The statuses that CONSUME a slot of the operator's daily apply budget.
    #: "submitted" is obvious. "unconfirmed" is an attempt whose click went
    #: out but whose confirmation could not be read: it may already have
    #: reached the employer, and the operator cannot un-send it, so the
    #: budget has to assume it was spent.
    BUDGET_CONSUMING_STATUSES = frozenset({"submitted", "unconfirmed"})

    def _is_live_unlocked(self, fingerprint: str) -> bool:
        """True when the posting is reserved, being submitted, or submitted.

        The ledger is APPEND-ONLY, so the presence of a fingerprint says only
        that it was seen at some point - the CURRENT status is what decides
        whether the posting may be applied to again.
        """
        self._reparse()
        return latest_status(self._entries, fingerprint) in self.LIVE_STATUSES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def entries(self) -> list[dict]:
        """One entry per APPLICATION (the latest line for each fingerprint).

        The ledger is append-only, so one application owns several lines:
        the reservation, the "submitting" mark, the "submitted" mark. A
        consumer that wants to know "which applications do I have" wants one
        row per application, not one per line - and a consumer that counts
        MATCHES would otherwise see every application twice and call the
        match ambiguous.

        The raw, append-only history is still on disk and still readable
        through :attr:`history`; this is the per-application view.

        The ``title`` and ``company`` of each row carry the NORMALISED
        MATCHING KEY, because that is the field a consumer compares against
        a tracker card (Indeed appends the location to the card title and
        punctuates the company differently). The values the posting
        actually carried are kept in ``raw_title`` and ``raw_company``, and
        in :attr:`history`.
        """
        self._reparse()
        rows = []
        for entry in latest_by_fingerprint(self._entries).values():
            row = dict(entry)
            row.setdefault("match_title", normalise_text(strip_location_suffix(str(entry.get("title", "")))))
            row.setdefault("match_company", normalise_text(str(entry.get("company", ""))))
            row["title"] = row["match_title"]
            row["company"] = row["match_company"]
            row.setdefault("raw_title", str(entry.get("title", "")))
            row.setdefault("raw_company", str(entry.get("company", "")))
            rows.append(row)
        return rows

    @property
    def history(self) -> list[dict]:
        """Every line of the ledger, in the order it was written.

        The raw, append-only history - one row per status change. This is
        what a reader needs when it wants to see the SEQUENCE (a
        reservation, then "submitting", then "submitted"), rather than the
        current state of each application.
        """
        self._reparse()
        return list(self._entries)

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
            # fingerprint since we last looked. Only a LIVE status blocks a
            # new attempt; a released one must stay retryable.
            if self._is_live_unlocked(fingerprint):
                return False

            self._append_line(
                {
                    "fingerprint": fingerprint,
                    "jk": jk,
                    "indeed_url": indeed_url,
                    # The RAW title and company are kept as they are: they
                    # are what the posting said, and the response monitor
                    # reports them to the operator.
                    "company": company,
                    "title": title,
                    # The MATCHING KEY is normalised: the tracker card
                    # renders the title with a location suffix and the
                    # company with different punctuation, so an exact
                    # comparison never fired and the mirror stayed empty.
                    "match_company": normalise_text(company),
                    "match_title": normalise_text(strip_location_suffix(title)),
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
        return metadata_for(self._entries, fingerprint)

    def status_of(self, fingerprint: str) -> str | None:
        """Return the latest status recorded for a fingerprint."""
        self._reparse()
        return latest_status(self._entries, fingerprint)

    def reservation_age(self, fingerprint: str, now: datetime | None = None) -> float | None:
        """Seconds since the posting was reserved, or None if it is not reserved.

        A run that is killed mid-application leaves a "reserved" line behind.
        The caller uses the age to expire that stale reservation, so the posting
        is not blocked forever.
        """
        self._reparse()
        moment = now or datetime.now(timezone.utc)
        return reservation_age(self._entries, fingerprint, moment)

    def submitted_today(self, now: datetime | None = None) -> int:
        """Count the postings submitted on the operator's CURRENT day.

        Each fingerprint counts once, using its LATEST status, so a posting
        that was marked more than once cannot inflate the count and wrongly
        block the operator's daily budget.

        The day boundary is the LOCAL day of *now* - not the UTC day. The
        budget is a promise to the operator ("at most N applications per
        day"), and the operator's day ends at their local midnight, not at
        UTC midnight. ``now`` carries the timezone that decides it; a naive
        ``now`` falls back to UTC.

        AN UNCONFIRMED ATTEMPT COUNTS AGAINST THE BUDGET. A submit click
        that was dispatched but whose confirmation could not be read may
        already have reached the employer. The operator cannot un-send it,
        so the budget has to assume it went out. Counting only "submitted"
        let a real attempt consume ZERO daily budget, and a run could then
        fire an unbounded number of applications at employers after the
        limit was supposed to be reached - the exact opposite of what the
        limit is for.
        """
        self._reparse()
        moment = now or datetime.now(timezone.utc)

        latest = latest_by_fingerprint(self._entries)

        count = 0
        for entry in latest.values():
            if entry.get("status") not in ApplicationLedger.BUDGET_CONSUMING_STATUSES:
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
            if same_budget_day(when, moment):
                count += 1
        return count
