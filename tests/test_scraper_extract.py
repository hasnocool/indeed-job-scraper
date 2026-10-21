"""Functional tests for the job-card extractor against a synthetic DOM.

Indeed's current mosaic card layout exposes the posted age as a plain badge
("New", "3 days ago") with no ``job-age`` testid, so the extractor falls back
to a pattern scan. These tests pin that behaviour without touching the network
or a real session: a page is built in memory and the real extractor runs
against it.

The tests skip when no Chromium binary is installed, so the suite still runs
on machines without browsers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indeed_scraper.scraper import extract_jobs

CARD = """
<div class="job_seen_beacon" data-jk="abc123">
  <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="abc123">
    <span>Senior Data Engineer</span></a></h2>
  <div class="css-j160pq"><div class="mosaic-provider-jobcards-1bj97w3">New</div></div>
  <div class="company_location">
    <span data-testid="company-name">Northwind Analytics</span>
    <div data-testid="text-location">Vancouver, BC</div>
  </div>
  <ul class="heading6 tapItem-gutter metadataContainer">
    <li data-testid="attribute_snippet_testid" class="salary-snippet-container">$120,000 a year</li>
    <li data-testid="attribute_snippet_testid">Full-time</li>
  </ul>
</div>
"""

AGED_CARD = CARD.replace(
    '<div class="mosaic-provider-jobcards-1bj97w3">New</div>',
    '<div class="mosaic-provider-jobcards-1bj97w3">3 days ago</div>',
)


def _page():
    """A Playwright page with the synthetic card, or skip the test."""
    playwright = pytest.importorskip("playwright.sync_api")
    binaries = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    if not binaries:
        pytest.skip("no Playwright Chromium binary installed")
    pw = playwright.sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    return pw, browser, page


@pytest.fixture()
def page():
    pw, browser, page = _page()
    try:
        yield page
    finally:
        browser.close()
        pw.stop()


def test_extracts_mosaic_card_fields(page) -> None:
    page.set_content(CARD)
    jobs = extract_jobs(page)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.jk == "abc123"
    assert job.title == "Senior Data Engineer"
    assert job.company == "Northwind Analytics"
    assert job.location == "Vancouver, BC"
    assert job.salary == "$120,000 a year"
    assert job.schedule == "Full-time"
    assert job.url.endswith("jk=abc123")


def test_extracts_posted_age_badge(page) -> None:
    page.set_content(CARD)
    jobs = extract_jobs(page)
    assert jobs[0].posted == "New"


def test_extracts_relative_posted_age(page) -> None:
    page.set_content(AGED_CARD)
    jobs = extract_jobs(page)
    assert jobs[0].posted == "3 days ago"


def test_posted_is_empty_without_an_age_badge(page) -> None:
    page.set_content(CARD.replace('<div class="mosaic-provider-jobcards-1bj97w3">New</div>', ""))
    jobs = extract_jobs(page)
    assert jobs[0].posted == ""
