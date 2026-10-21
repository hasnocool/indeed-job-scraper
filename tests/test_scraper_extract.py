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
    <li data-testid="attribute_snippet_testid">Day shift</li>
  </ul>
</div>
"""

AGED_CARD = CARD.replace(
    '<div class="mosaic-provider-jobcards-1bj97w3">New</div>',
    '<div class="mosaic-provider-jobcards-1bj97w3">3 days ago</div>',
)

# Indeed rotates the order of the attribute chips between runs, so the same
# posting can show "Full-time" first on one visit and "Day shift" first on the
# next. The extractor therefore collects every chip, sorted, so the value (and
# the fingerprint built from it) stays stable across runs.
SHIFTED_CARD = """
<div class="job_seen_beacon" data-jk="abc123">
  <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="abc123">
    <span>Senior Data Engineer</span></a></h2>
  <div class="company_location">
    <span data-testid="company-name">Northwind Analytics</span>
    <div data-testid="text-location">Vancouver, BC</div>
  </div>
  <ul class="heading6 tapItem-gutter metadataContainer">
    <li data-testid="attribute_snippet_testid">Day shift</li>
    <li data-testid="attribute_snippet_testid" class="salary-snippet-container">$120,000 a year</li>
    <li data-testid="attribute_snippet_testid">Full-time</li>
  </ul>
</div>
"""


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
    assert job.schedule == "Day shift; Full-time"
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


def test_schedule_is_stable_across_attribute_chip_order(page) -> None:
    """Indeed rotates chip order between runs; the value must not change."""
    page.set_content(CARD)
    first = extract_jobs(page)
    page.set_content(SHIFTED_CARD)
    second = extract_jobs(page)
    # Same chips, different DOM order -> identical schedule value.
    assert first[0].schedule == "Day shift; Full-time"
    assert second[0].schedule == first[0].schedule


def test_schedule_collects_all_attribute_chips(page) -> None:
    page.set_content(SHIFTED_CARD)
    jobs = extract_jobs(page)
    assert jobs[0].schedule == "Day shift; Full-time"
    # The salary chip must not leak into the schedule field.
    assert "$120,000" not in jobs[0].schedule
    assert jobs[0].salary == "$120,000 a year"
