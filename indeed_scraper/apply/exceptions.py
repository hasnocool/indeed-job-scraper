"""Exceptions raised during the apply flow."""

from __future__ import annotations

from indeed_scraper.errors import IndeedScraperError


class ApplyError(IndeedScraperError):
    """Base class for apply-flow failures."""


class ApplyBlockedError(ApplyError):
    """Apply could not proceed (CAPTCHA, Cloudflare, auth wall, etc.)."""


class FieldMissingError(ApplyError):
    """A required form field is missing from the job page."""

    def __init__(self, question: str, job_url: str) -> None:
        self.question = question
        self.job_url = job_url
        super().__init__(f"Missing field '{question}' on {job_url}")


class ProfileNotFoundError(ApplyError):
    """Profile data could not be loaded."""


class RiskBudgetExceededError(ApplyError):
    """The daily apply limit has been exceeded."""


class PortalNavigationError(ApplyError):
    """Could not navigate to the apply portal."""