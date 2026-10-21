"""Typed errors raised across the scraper's boundaries.

Re-exported from :mod:`indeed_scraper.apply.exceptions` so the apply flow and
its callers share one definition.
"""

from __future__ import annotations

from indeed_scraper.apply.exceptions import (
    ApplyBlockedError,
    ApplyError,
    FieldMissingError,
    PortalNavigationError,
    ProfileNotFoundError,
    RiskBudgetExceededError,
)

__all__ = [
    "ApplyBlockedError",
    "ApplyError",
    "FieldMissingError",
    "PortalNavigationError",
    "ProfileNotFoundError",
    "RiskBudgetExceededError",
]
