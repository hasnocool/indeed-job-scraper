"""Single source of truth for paths, search scope, pacing and timeouts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent

DEFAULT_QUERY = ""  # empty means "every job in the location"
DEFAULT_LOCATIONS: tuple[str, ...] = ("Ucluelet, BC", "Tofino, BC", "Port Alberni, BC")
DEFAULT_SITE = "ca.indeed.com"


def site_country(site: str) -> str:
    """Indeed region code for a host: ca.indeed.com -> CA, www.indeed.com -> US."""
    return "CA" if site.startswith("ca.") else "US"
DEFAULT_MAX_PAGES = 10
DEFAULT_LOGIN_TIMEOUT_S = 600
DEFAULT_PAGE_DELAY_S = 7.0


@dataclass(frozen=True, slots=True)
class SearchParams:
    """One Indeed search request set, across one or more locations."""

    query: str = DEFAULT_QUERY
    locations: tuple[str, ...] = DEFAULT_LOCATIONS
    max_pages: int = DEFAULT_MAX_PAGES

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", self.query.strip())
        cleaned: list[str] = []
        for location in self.locations:
            name = location.strip()
            if name and name not in cleaned:
                cleaned.append(name)
        if not cleaned:
            raise ValueError("at least one location is required")
        if self.max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        object.__setattr__(self, "locations", tuple(cleaned))


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved runtime configuration; everything else depends on it."""

    state_dir: Path
    site: str = DEFAULT_SITE
    headless: bool = False
    page_delay_s: float = DEFAULT_PAGE_DELAY_S
    login_timeout_s: int = DEFAULT_LOGIN_TIMEOUT_S
    navigation_timeout_ms: int = 45_000
    challenge_timeout_s: int = 180

    @property
    def profile_dir(self) -> Path:
        return self.state_dir / "chrome-profile"

    @property
    def cookies_dir(self) -> Path:
        return self.state_dir / "cookies"

    @property
    def sessions_dir(self) -> Path:
        return self.cookies_dir / "sessions"

    @property
    def current_cookie_file(self) -> Path:
        return self.cookies_dir / "current.json"

    @property
    def history_file(self) -> Path:
        return self.cookies_dir / "history.jsonl"

    @property
    def runs_dir(self) -> Path:
        return self.state_dir / "runs"

    @property
    def latest_dir(self) -> Path:
        return self.state_dir / "latest"

    @property
    def master_dir(self) -> Path:
        return self.state_dir / "master"

    # output_dir is replaced by runs_dir/latest_dir/master_dir; kept for backward compat
    @property
    def output_dir(self) -> Path:
        return self.state_dir / "output"

    @property
    def country_code(self) -> str:
        return site_country(self.site)

    def ensure_dirs(self) -> None:
        for path in (
            self.state_dir,
            self.profile_dir,
            self.cookies_dir,
            self.sessions_dir,
            self.runs_dir,
            self.latest_dir,
            self.master_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(
        cls,
        *,
        state_dir: Path | None = None,
        site: str | None = None,
        headless: bool = False,
        page_delay_s: float | None = None,
        login_timeout_s: int | None = None,
    ) -> Config:
        raw_root = os.environ.get("INDEED_STATE_DIR")
        root = state_dir or (Path(raw_root) if raw_root else REPO_ROOT / "data")
        chosen_site = site or os.environ.get("INDEED_SITE") or DEFAULT_SITE
        delay = DEFAULT_PAGE_DELAY_S if page_delay_s is None else page_delay_s
        timeout = DEFAULT_LOGIN_TIMEOUT_S if login_timeout_s is None else login_timeout_s
        if delay < 0:
            raise ValueError("page_delay_s must not be negative")
        if timeout < 1:
            raise ValueError("login_timeout_s must be >= 1")
        if "/" in chosen_site or "://" in chosen_site:
            raise ValueError("site must be a host name such as ca.indeed.com")
        return cls(
            state_dir=root.expanduser().resolve(),
            site=chosen_site.strip().lower(),
            headless=headless,
            page_delay_s=delay,
            login_timeout_s=timeout,
        )
