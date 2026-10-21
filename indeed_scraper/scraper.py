"""Job search scraping across several locations over a signed-in session."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote_plus, urljoin

from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console

from .browser import (
    active_page,
    challenge_kind,
    challenge_label,
    goto,
    open_context,
    wait_for_challenge,
)
from .config import Config, SearchParams, site_country
from .cookies import CookieSession, CookieStore, cookies_from_playwright, utcnow
from .errors import ChallengeBlockedError, SessionExpiredError

JOBS_PER_PAGE = 10
MAX_START = 1000

_CARD_FIELDS = ("title", "company", "location", "salary", "schedule", "posted", "snippet", "url")

_EXTRACT_JS = r"""(() => {
  const best = new Map();
  const fields = ['title', 'company', 'location', 'salary', 'schedule', 'posted', 'snippet', 'url'];
  const blank = (jk) => {
    const record = { jk: jk };
    for (const field of fields) record[field] = '';
    return record;
  };
  const clean = (value) => (value || '').split(String.fromCharCode(10)).join(' ').split(String.fromCharCode(160)).join(' ').replace(/ {2,}/g, ' ').trim();
  const text = (node) => clean(node && node.innerText ? node.innerText : '');
  const pick = (el, sels) => {
    for (const sel of sels) {
      const node = el.querySelector(sel);
      const value = text(node);
      if (value) return value;
    }
    return '';
  };
  const add = (jk, field, value) => {
    if (!value) return;
    const record = best.get(jk) || blank(jk);
    if (!record[field]) record[field] = value;
    best.set(jk, record);
  };
  for (const el of document.querySelectorAll('[data-jk]')) {
    const jk = el.getAttribute('data-jk');
    if (!jk) continue;
    const anchor = el.matches('a[data-jk]') ? el : el.querySelector('a[data-jk], a.jcs-JobTitle, h2 a, a[href*="viewjob"]');
    const card = el.closest('div.job_seen_beacon, li, div.cardOutline, div.result') || el.parentElement || el;
    add(jk, 'title', text(anchor) || pick(card, ['h2']));
    add(jk, 'company', pick(card, ['[data-testid="company-name"]', '.companyName', '[data-company-name]']));
    add(jk, 'location', pick(card, ['[data-testid="text-location"]', '.companyLocation', '[data-testid="job-location"]']));
    add(jk, 'salary', pick(card, ['li.salary-snippet-container', '.salary-snippet-container', '.salary-snippet', '.estimated-salary', '[data-testid="salary-snippet"]']));
    add(jk, 'schedule', pick(card, ['li[data-testid="attribute_snippet_testid"]:not(.salary-snippet-container)', '.jobTitleSnippet']));
    add(jk, 'posted', pick(card, ['[data-testid="job-age"]', 'span.date', '.date', '[data-testid="myJobsStateDate"]']));
    add(jk, 'snippet', pick(card, ['.job-snippet', '[data-testid="belowJobSnippet"]', '.summary']).slice(0, 400));
    add(jk, 'url', 'https://www.indeed.com/viewjob?jk=' + jk);
  }
  return Array.from(best.values());
})()"""

_NEXT_JS = r"""(() => {
  const node = document.querySelector('a[data-testid="pagination-page-next"], a[aria-label="Next Page"], nav a[aria-label="Next"], a[aria-label="Next"]');
  return node ? node.getAttribute('href') : null;
})()"""


class Job(BaseModel):
    model_config = ConfigDict(frozen=True)

    jk: str = Field(min_length=1)
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    schedule: str = ""
    posted: str = ""
    snippet: str = ""
    url: str = ""
    # Which of the searched locations actually surfaced this posting.
    matches: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocationReport:
    location: str
    pages: int
    found: int
    stopped_reason: str


@dataclass(frozen=True, slots=True)
class ScrapeResult:
    params: SearchParams
    jobs: tuple[Job, ...]
    pages: int
    reports: tuple[LocationReport, ...]
    session: CookieSession
    scraped_at: datetime


def search_url(params: SearchParams, location: str, *, site: str, start: int = 0) -> str:
    place = quote_plus(location)
    country = site_country(site)
    keyword = f"&q={quote_plus(params.query)}" if params.query else ""
    return f"https://{site}/jobs?l={place}{keyword}&start={start}&sort=date&co={country}"


def extract_jobs(page: object) -> list[Job]:
    raw = page.evaluate(_EXTRACT_JS)
    jobs: list[Job] = []
    if not isinstance(raw, list):
        return jobs
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            jobs.append(Job.model_validate(item))
        except ValueError:
            continue
    return jobs


def merge_job(existing: Job | None, incoming: Job, location: str) -> Job:
    """Merge duplicates seen in several location searches, keeping the fullest fields."""
    if existing is None:
        return incoming.model_copy(update={"matches": (location,)})
    updates: dict[str, str] = {}
    for field in _CARD_FIELDS:
        current = str(getattr(existing, field))
        candidate = str(getattr(incoming, field))
        updates[field] = current if len(current) >= len(candidate) else candidate
    matches = tuple(dict.fromkeys((*existing.matches, location)))
    return existing.model_copy(update={**updates, "matches": matches})


def next_page_url(page: object) -> str | None:
    href = page.evaluate(_NEXT_JS)
    if not isinstance(href, str) or not href:
        return None
    return urljoin(page.url, href)


def _clear_challenge(page: object, config: Config, console: Console) -> None:
    kind = challenge_kind(page)
    if kind == "auth":
        raise SessionExpiredError(
            "Indeed asked for sign-in while scraping; the saved session is no longer valid."
        )
    if kind == "none":
        return
    console.print(
        f"[yellow]{challenge_label(kind)} — solve it in the browser window if it is visible…[/yellow]"
    )
    kind = wait_for_challenge(page, timeout_s=config.challenge_timeout_s)
    if kind == "auth":
        raise SessionExpiredError(
            "Indeed asked for sign-in while scraping; the saved session is no longer valid."
        )
    if kind != "none":
        raise ChallengeBlockedError(f"Could not clear {challenge_label(kind)}.")


def _scrape_location(
    config: Config,
    params: SearchParams,
    location: str,
    page: object,
    collected: dict[str, Job],
    console: Console,
) -> LocationReport:
    pages = 0
    found = 0
    stopped_reason = "max_pages"
    url: str | None = search_url(params, location, site=config.site)
    while url is not None and pages < params.max_pages:
        goto(page, url, config)
        page.wait_for_timeout(2500)
        _clear_challenge(page, config, console)

        batch = extract_jobs(page)
        if not batch:
            stopped_reason = "no_jobs"
            break
        fresh = 0
        for job in batch:
            before = collected.get(job.jk)
            collected[job.jk] = merge_job(before, job, location)
            if before is None:
                fresh += 1
        if fresh == 0:
            stopped_reason = "no_new_jobs"
            break
        pages += 1
        found += fresh
        console.print(
            f"[green]{location}[/green] page {pages}: +{fresh} jobs (total {len(collected)})"
        )

        discovered = next_page_url(page)
        if discovered is not None:
            url = discovered
        else:
            fallback_start = pages * JOBS_PER_PAGE
            url = (
                search_url(params, location, site=config.site, start=fallback_start)
                if fallback_start <= MAX_START
                else None
            )
        if url is not None:
            time.sleep(config.page_delay_s + time.monotonic() % 2.0)
    return LocationReport(location=location, pages=pages, found=found, stopped_reason=stopped_reason)


def run_scrape(
    config: Config,
    params: SearchParams,
    session: CookieSession,
    store: CookieStore,
    console: Console,
) -> ScrapeResult:
    """Search every location, dedupe by job key and refresh cookies on exit."""
    collected: dict[str, Job] = {}
    reports: list[LocationReport] = []
    current = session

    with open_context(config, session=session) as context:
        page = active_page(context)
        try:
            for location in params.locations:
                console.print(
                    f"[cyan]Searching[/cyan] {params.query or 'all jobs'} in {location}…"
                )
                reports.append(
                    _scrape_location(config, params, location, page, collected, console)
                )
        except KeyboardInterrupt:
            console.print("[yellow]Interrupted — keeping the jobs collected so far.[/yellow]")
            reports.append(
                LocationReport(
                    location="(interrupted)", pages=0, found=0, stopped_reason="interrupted"
                )
            )
        finally:
            fresh_cookies = cookies_from_playwright(context.cookies())
            if fresh_cookies and current.is_signed_in():
                current = store.refresh(
                    current,
                    cookies=fresh_cookies,
                    notes=(f"scrape: {sum(report.pages for report in reports)} pages",),
                )

    return ScrapeResult(
        params=params,
        jobs=tuple(collected.values()),
        pages=sum(report.pages for report in reports),
        reports=tuple(reports),
        session=current,
        scraped_at=utcnow(),
    )
