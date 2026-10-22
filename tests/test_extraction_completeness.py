"""Drift gate: the real extractor must keep every job-card field populated.

This test runs the REAL extractor (``indeed_scraper.scraper.extract_jobs``)
against a committed / representative search-page fixture and asserts a
per-field completeness floor. If Indeed's markup changes again, this suite
goes RED instead of silently shipping an empty field.

STATUS / CAVEAT
---------------
A live capture of the current Indeed DOM was BLOCKED (Indeed refused the
saved session; see scripts/capture_search_page.py). The fixture below is
therefore a RECONSTRUCTED representative of the observed mosaic card layout
(pinned in tests/test_scraper_extract.py) and is PENDING a live capture.

It deliberately contains NO ``.job-snippet`` / ``[data-testid="belowJobSnippet"]``
/ ``.summary`` element inside the card container, mirroring the measured live
defect where ``snippet`` is empty in 98/98 records. Consequently this test
currently FAILS on the snippet floor — which is exactly the drift it is
designed to detect. It is marked ``xfail(strict=True)`` so the suite stays a
usable gate while the defect is open, and so that it FAILS LOUDLY as soon as
the extractor is fixed: a strict xfail that unexpectedly passes is a suite
error, and the marker must be removed then. Once a live capture is obtained
and the extractor is fixed against it, the fixture should be replaced with the
real DOM and this test should turn GREEN.

The extractor tests in tests/test_scraper_extract.py use hand-written
synthetic DOM with no snippet element, so they stay green while the real
field was 100% dead; this gate closes that gap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indeed_scraper.scraper import extract_jobs

# Thresholds (fractions of cards that must have the field populated).
MIN_SNIPPET_RATIO = 0.90
MIN_COMPANY_RATIO = 0.90
MIN_LOCATION_RATIO = 0.90

# RECONSTRUCTED fixture (pending live capture). Mosaic card layout matching
# the observed structure; snippet element is ABSENT to mirror the live defect.
FIXTURE_HTML = """
<!DOCTYPE html>
<html><body>
<div id="mosaic-provider-jobcards">
  <div class="job_seen_beacon" data-jk="rec000001">
    <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="rec000001"><span>Senior Data Engineer</span></a></h2>
    <div class="company_location">
      <span data-testid="company-name">Northwind Analytics</span>
      <div data-testid="text-location">Vancouver, BC</div>
    </div>
    <ul class="heading6 tapItem-gutter metadataContainer">
      <li data-testid="attribute_snippet_testid" class="salary-snippet-container">$120,000 a year</li>
      <li data-testid="attribute_snippet_testid">Full-time</li>
      <li data-testid="attribute_snippet_testid">Day shift</li>
    </ul>
    <div class="mosaic-provider-jobcards-1bj97w3">New</div>
  </div>

  <div class="job_seen_beacon" data-jk="rec000002">
    <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="rec000002"><span>Product Manager</span></a></h2>
    <div class="company_location">
      <span data-testid="company-name">Globex Corp</span>
      <div data-testid="text-location">Toronto, ON</div>
    </div>
    <ul class="heading6 tapItem-gutter metadataContainer">
      <li data-testid="attribute_snippet_testid" class="salary-snippet-container">$95,000 a year</li>
      <li data-testid="attribute_snippet_testid">Full-time</li>
    </ul>
    <div class="mosaic-provider-jobcards-1bj97w3">3 days ago</div>
  </div>

  <div class="job_seen_beacon" data-jk="rec000003">
    <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="rec000003"><span>DevOps Engineer</span></a></h2>
    <div class="company_location">
      <span data-testid="company-name">Umbrella Corp</span>
      <div data-testid="text-location">Montreal, QC</div>
    </div>
    <ul class="heading6 tapItem-gutter metadataContainer">
      <li data-testid="attribute_snippet_testid">Remote</li>
      <li data-testid="attribute_snippet_testid" class="salary-snippet-container">$110,000 a year</li>
    </ul>
    <div class="mosaic-provider-jobcards-1bj97w3">1 week ago</div>
  </div>

  <div class="job_seen_beacon" data-jk="rec000004">
    <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="rec000004"><span>Data Analyst</span></a></h2>
    <div class="company_location">
      <span data-testid="company-name">Stark Industries</span>
      <div data-testid="text-location">Calgary, AB</div>
    </div>
    <ul class="heading6 tapItem-gutter metadataContainer">
      <li data-testid="attribute_snippet_testid" class="salary-snippet-container">$80,000 a year</li>
      <li data-testid="attribute_snippet_testid">Part-time</li>
    </ul>
    <div class="mosaic-provider-jobcards-1bj97w3">Yesterday</div>
  </div>

  <div class="job_seen_beacon" data-jk="rec000005">
    <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="rec000005"><span>Software Engineer</span></a></h2>
    <div class="company_location">
      <span data-testid="company-name">Wayne Enterprises</span>
      <div data-testid="text-location">Ottawa, ON</div>
    </div>
    <ul class="heading6 tapItem-gutter metadataContainer">
      <li data-testid="attribute_snippet_testid" class="salary-snippet-container">$105,000 a year</li>
      <li data-testid="attribute_snippet_testid">Full-time</li>
      <li data-testid="attribute_snippet_testid">Day shift</li>
    </ul>
    <div class="mosaic-provider-jobcards-1bj97w3">Just posted</div>
  </div>
</div>
</body></html>
"""


def _page():
    """A Playwright page holding the fixture, or skip the test."""
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "OPEN DEFECT - extraction drift. `snippet` is empty in 98/98 records of "
        "data/master/jobs_master.json (100%, every run) and 40/98 `posted` is "
        "empty; the exported master CSV therefore has an empty 'Job Description' "
        "column in 98/98 rows. The selector fix CANNOT be written blind: it needs "
        "a real capture of the current Indeed DOM, and the capture was BLOCKED "
        "(Indeed refused the saved session - see scripts/capture_search_page.py). "
        "This test is the drift gate and it is RED on purpose. It is marked "
        "xfail(strict=True) rather than skipped so the suite stays a usable gate, "
        "and so that it FAILS LOUDLY the moment the extractor is fixed: a strict "
        "xfail that unexpectedly passes is a suite error, so the marker must be "
        "removed then, and the fixture replaced with the real DOM."
    ),
)
def test_extraction_completeness_floor(page) -> None:
    """Per-field completeness floor against the reconstructed search fixture.

    company and location must be populated on >= 90% of cards; snippet must be
    populated on >= 90% and is hard-asserted to be non-zero overall.
    """
    page.set_content(FIXTURE_HTML)
    jobs = extract_jobs(page)
    total = len(jobs)
    assert total > 0, "no cards extracted from fixture"

    counts = {
        field: sum(1 for j in jobs if str(getattr(j, field)).strip())
        for field in ("title", "company", "location", "salary", "schedule", "posted", "snippet", "url")
    }

    def ratio(field: str) -> float:
        return counts[field] / total

    # Company and location: the card container resolution still works.
    assert ratio("company") >= MIN_COMPANY_RATIO, (
        f"company fill rate {counts['company']}/{total} below {MIN_COMPANY_RATIO:.0%}"
    )
    assert ratio("location") >= MIN_LOCATION_RATIO, (
        f"location fill rate {counts['location']}/{total} below {MIN_LOCATION_RATIO:.0%}"
    )

    # Snippet: hard assertion that the field is not 0%. With the reconstructed
    # fixture (no snippet element in the card container) this is 0% and this
    # assertion fails — the drift gate catching the live defect.
    assert counts["snippet"] > 0, (
        f"snippet is empty on {counts['snippet']}/{total} cards (0%) — "
        f"extraction drift: the description selector no longer matches Indeed's DOM"
    )
    assert ratio("snippet") >= MIN_SNIPPET_RATIO, (
        f"snippet fill rate {counts['snippet']}/{total} below {MIN_SNIPPET_RATIO:.0%}"
    )
