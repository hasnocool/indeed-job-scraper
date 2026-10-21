"""Hash-based deduplication for Indeed job records."""

from __future__ import annotations

import hashlib
import json

FINGERPRINT_VERSION = 1
"""Version string for fingerprint format; bump on incompatible field changes."""

FINGERPRINT_FIELDS = ("title", "company", "location", "salary", "schedule")
"""Fields used to compute a content fingerprint; excludes jk, url, posted, snippet, matches."""


def job_fingerprint(job) -> str:
    """Compute a SHA-256 hexdigest from the canonical fingerprint fields.

    The fingerprint uses only FINGERPRINT_FIELDS; it deliberately excludes
    ``jk``, ``url``, ``posted``, ``snippet``, and ``matches`` so that
    identical content posted under different keys (re-post detection) is
    caught, while age‐drift fields (``posted``) and per‐run context
    (``snippet``, ``matches``) are ignored.

    Docstring‐level design:
      - excludes jk+url so identical content under different keys is caught
      - excludes posted (relative-age drift between runs)
      - excludes snippet (variable truncation)
      - excludes matches (per-run context)
    """
    data: dict[str, str] = {}
    for field in FINGERPRINT_FIELDS:
        value = getattr(job, field, "") or ""
        data[field] = value
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def short_id(fingerprint: str) -> str:
    """Return the first 12 hex characters of a fingerprint as a readable ID."""
    return fingerprint[:12]