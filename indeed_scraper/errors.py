"""Typed errors raised across the scraper's boundaries."""

from __future__ import annotations


class IndeedScraperError(Exception):
    """Base class for every expected failure of the scraper."""


class SessionMissingError(IndeedScraperError):
    """No saved Indeed session exists yet; the user must sign in."""


class SessionExpiredError(IndeedScraperError):
    """Indeed rejected the saved session; a fresh sign-in is required."""


class LoginTimeoutError(IndeedScraperError):
    """The human did not finish signing in before the deadline."""


class ChallengeBlockedError(IndeedScraperError):
    """Cloudflare/Indeed verification could not be cleared."""


class ScrapeError(IndeedScraperError):
    """The job listings could not be extracted from a page."""
