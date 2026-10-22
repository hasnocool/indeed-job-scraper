"""Type definitions shared across the Indeed scraper.

Re-exported from :mod:`indeed_scraper.apply.types` so both the apply
subpackage and its callers share one definition.
"""

from __future__ import annotations

from indeed_scraper.apply.types import (
    ApplyData,
    ApplyResult,
    ApplyStatus,
    PortalType,
    SubmitResult,
)

__all__ = ["ApplyData", "ApplyResult", "ApplyStatus", "PortalType", "SubmitResult"]
