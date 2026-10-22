"""Exceptions raised during the apply flow."""

from __future__ import annotations

from indeed_scraper.errors import IndeedScraperError


class ApplyError(IndeedScraperError):
    """Base class for apply-flow failures."""


class ApplyBlockedError(ApplyError):
    """Apply could not proceed (CAPTCHA, Cloudflare, auth wall, etc.).

    The exception carries the KIND of block and the URL it happened on, and
    it has a proper ``__str__``. That matters more than it looks: the
    exception's ``__init__`` never called ``super().__init__(...)``, so
    ``str(error)`` was the REPR OF ITS ARGS TUPLE -
    ``"('Indeed security check', 'https://x')"`` - which never contained
    the word "challenge". The flow built the result detail from
    ``str(error)``, and ``exit_code_for`` decides "a challenge stopped
    this run" by looking for that word. So a real "Indeed security check"
    wall exited 2 ("attempt failed") instead of 3 ("back off").

    ``__str__`` now returns the challenge KIND, so the marker survives
    every path that formats the error.
    """

    def __init__(self, challenge: str, job_url: str = "") -> None:
        self.challenge = challenge
        self.job_url = job_url
        super().__init__(challenge)

    def __str__(self) -> str:
        """The challenge kind, not the args tuple.

        The kind is what the caller needs and what the exit-code contract
        looks for; the URL is available on the attribute for anyone who
        wants it.
        """
        return self.challenge


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