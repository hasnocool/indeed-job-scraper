"""Failing-first regression tests for lane A's four confirmed defects.

Each test here fails on the UNFIXED code and passes on the fixed code:

* **A1** - ``submit_application`` reported a success it never observed, and
  clicked the submit button a SECOND time when the post-click read raised.
* **A2** - a bare HTML5 ``required`` attribute read as *not* required, so the
  hard-refuse never fired and a required field could be left empty.
* **A3** - the draft claimed fields that were never filled.
* **A4** - ``RiskBudget.delay_seconds`` raised ``AttributeError`` on the
  ``now is None`` branch, so the CLI crashed on the second application.

A2 and A3 are driven against a REAL Chromium page (``page.set_content``):
the fake locator in ``tests/test_indeed_form.py`` could not return ``''`` for
a boolean attribute, which is precisely why the bug survived. The browser is
launched headless and always closed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from indeed_scraper.apply.exceptions import FieldMissingError
from indeed_scraper.apply.indeed_form import fill_indeed_form, submit_application
from indeed_scraper.apply.profile import Profile
from indeed_scraper.apply.risk import RiskBudget

#: The submit controls ``submit_application`` looks for. In a real page
#: ``button:has-text("Submit")`` ALSO matches a "Submit application" button,
#: which is how the old code clicked the same button twice.
SUBMIT_SELECTORS = (
    'button:has-text("Submit application")',
    'button:has-text("Submit")',
    'input[type="submit"]',
    '[data-testid="submit-application"]',
)


# ---------------------------------------------------------------------------
# Real-browser fixture (A2 and A3 need a faithful DOM)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_page():
    """A REAL headless Chromium page, or skip the test.

    The fixture is MODULE-scoped on purpose. A function-scoped fixture
    launched a fresh Chromium for every test, so the file took 275 seconds
    for 17 tests - almost all of it browser start-up. One browser for the
    module, with ``set_content`` per test, brings the file down to a few
    seconds.

    The page is still closed at the end of the module, so no browser is
    left running.
    """
    playwright = pytest.importorskip("playwright.sync_api")
    binaries = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    if not binaries:
        pytest.skip("no Playwright Chromium binary installed")
    pw = playwright.sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    try:
        yield page
    finally:
        browser.close()
        pw.stop()


def _resume(tmp_path: Path) -> str:
    """A real PDF on disk (the apply path refuses a placeholder)."""
    target = tmp_path / "resume.pdf"
    target.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    return str(target)


def _profile(tmp_path: Path, **overrides: str) -> Profile:
    values = {
        "name": "Ada",
        "email": "ada@example.com",
        "phone": "555-0100",
        "resume_path": _resume(tmp_path),
    }
    values.update(overrides)
    return Profile(**values)


# ---------------------------------------------------------------------------
# A2 - the bare `required` attribute must be visible
# ---------------------------------------------------------------------------

def test_a_bare_required_attribute_is_detected_on_a_real_page(real_page, tmp_path: Path) -> None:
    """A real browser reports a bare `required` as the EMPTY STRING.

    ``bool(required or aria_req)`` is therefore False for a React-rendered
    ``required=""``, the field is judged optional, and an empty required field
    is silently skipped instead of refused. The attribute's PRESENCE is what
    matters, not its truthiness.
    """
    real_page.set_content(
        '<html><body>'
        '<input name="applicant.name" required>'
        '<input id="applicant-email" required="">'
        '<input id="applicant-phone">'
        "</body></html>"
    )

    # The browser really does report '' for the boolean attribute.
    raw = real_page.locator('input[name="applicant.name"]').first.get_attribute("required")
    assert raw == "", f"expected the bare attribute to read as '', got {raw!r}"

    # The form filler must treat that field as REQUIRED: the profile has no
    # name, so the hard-refuse must fire.
    with pytest.raises(FieldMissingError) as excinfo:
        fill_indeed_form(real_page, _profile(tmp_path, name=""))

    assert excinfo.value.question
    assert excinfo.value.job_url


def test_an_optional_field_is_still_not_refused(real_page, tmp_path: Path) -> None:
    """The fix must not turn EVERY field into a required one."""
    real_page.set_content(
        '<html><body>'
        '<input name="applicant.name">'
        '<input id="applicant-email">'
        '<input id="applicant-phone">'
        "</body></html>"
    )

    # Nothing is required, so an empty profile value is simply skipped.
    draft = fill_indeed_form(real_page, _profile(tmp_path, name="", email="", phone=""))

    assert "name" not in draft


def test_aria_required_true_is_detected(real_page, tmp_path: Path) -> None:
    """`aria-required="true"` is required; `aria-required="false"` is not."""
    real_page.set_content(
        '<html><body>'
        '<input name="applicant.name" aria-required="true">'
        "</body></html>"
    )
    with pytest.raises(FieldMissingError):
        fill_indeed_form(real_page, _profile(tmp_path, name=""))

    real_page.set_content(
        '<html><body>'
        '<input name="applicant.name" aria-required="false">'
        "</body></html>"
    )
    draft = fill_indeed_form(real_page, _profile(tmp_path, name=""))
    assert "name" not in draft


def test_a_required_alternate_selector_is_detected(real_page, tmp_path: Path) -> None:
    """Every selector in the tuple is inspected, not only the first one.

    The first `name` selector matches nothing; the SECOND one is the required
    input that is actually on the form. Only checking field_sels[0] misses it.
    """
    real_page.set_content(
        '<html><body>'
        '<input id="applicant-name" required>'
        "</body></html>"
    )

    # The first selector of the "name" tuple matches nothing here.
    assert real_page.locator('input[name="applicant.name"]').count() == 0

    with pytest.raises(FieldMissingError):
        fill_indeed_form(real_page, _profile(tmp_path, name=""))


# ---------------------------------------------------------------------------
# A3 - the draft must be a truthful receipt
# ---------------------------------------------------------------------------

def test_a_form_with_no_inputs_claims_no_fields(real_page, tmp_path: Path) -> None:
    """A form with NO applicant inputs must not produce a filled draft.

    The live Indeed smartapply form had ZERO applicant inputs at fill time,
    yet the draft claimed fields ["email", "name", "phone"]. A draft is a
    receipt: it must list only what actually reached the form, and a form
    with nothing to fill is not a successful fill at all.
    """
    real_page.set_content(
        '<html><body><div id="smartapply">Nothing to fill here</div></body></html>'
    )

    with pytest.raises(FieldMissingError) as excinfo:
        fill_indeed_form(real_page, _profile(tmp_path))

    assert "no_fillable_fields" in str(excinfo.value), (
        f"expected a no-fillable-fields report, got: {excinfo.value!r}"
    )


def test_the_draft_lists_only_the_fields_that_were_filled(real_page, tmp_path: Path) -> None:
    """A field that is not on the form must not appear in the draft."""
    real_page.set_content(
        '<html><body>'
        '<input name="applicant.name">'
        '<input id="applicant-email">'
        "</body></html>"
    )

    draft = fill_indeed_form(real_page, _profile(tmp_path))

    assert "name" in draft
    assert "email" in draft
    assert "phone" not in draft, f"the draft claims a field that was never filled: {draft!r}"


def test_the_draft_records_a_resume_that_really_reached_the_form(real_page, tmp_path: Path) -> None:
    """The resume upload is recorded only when a file input took the file."""
    real_page.set_content(
        '<html><body>'
        '<input name="applicant.name">'
        '<input id="applicant-email">'
        '<input id="applicant-phone">'
        '<input type="file" id="resume-file">'
        "</body></html>"
    )

    draft = fill_indeed_form(real_page, _profile(tmp_path))

    assert "resume" in draft, f"the resume upload is not recorded: {draft!r}"


def test_the_draft_surfaces_a_resume_that_was_never_uploaded(real_page, tmp_path: Path) -> None:
    """A resume that was NOT uploaded must be surfaced, not hidden.

    This is the F10 case: the resume never reached the form and the old code
    swallowed it and produced a draft that looked complete.
    """
    real_page.set_content(
        '<html><body>'
        '<input name="applicant.name">'
        '<input id="applicant-email">'
        '<input id="applicant-phone">'
        "</body></html>"
    )

    draft = fill_indeed_form(real_page, _profile(tmp_path))

    assert "resume" not in draft, f"an un-uploaded resume must not be claimed: {draft!r}"
    assert draft.get("resume_status") == "no_input", (
        f"the missing resume must be surfaced honestly: {draft!r}"
    )


# ---------------------------------------------------------------------------
# A4 - the risk budget's clock
# ---------------------------------------------------------------------------

def test_delay_seconds_with_now_none_returns_a_number() -> None:
    """`now=None` must not raise: the CLI hits this on the second application."""
    budget = RiskBudget(min_delay_minutes=30.0)
    last = datetime.now(tz=timezone.utc) - timedelta(minutes=1)

    remaining = budget.delay_seconds(last)

    assert isinstance(remaining, float)
    assert remaining > 0.0


def test_delay_seconds_with_now_none_and_a_naive_last_submit() -> None:
    """A naive timestamp must not raise either."""
    budget = RiskBudget(min_delay_minutes=30.0)
    last = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)

    remaining = budget.delay_seconds(last)

    assert isinstance(remaining, float)


def test_a_non_positive_daily_cap_never_disables_the_limit(tmp_path: Path) -> None:
    """A cap of 0 must BLOCK every application, not allow every application.

    `max_per_day <= 0` used to return True ("no limit"), so a misconfigured or
    hostile cap silently disabled the daily budget altogether.
    """
    from indeed_scraper.apply.ledger import ApplicationLedger

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")

    assert RiskBudget(max_per_day=0).can_apply(ledger) is False
    assert RiskBudget(max_per_day=-1).can_apply(ledger) is False


def test_an_unconfirmed_attempt_consumes_the_daily_budget(tmp_path: Path) -> None:
    """An UNCONFIRMED attempt must count against the daily budget.

    The submit click may have reached the employer even though the
    confirmation could not be read. The operator cannot un-send it, so the
    budget has to assume it went out.

    Counting only "submitted" let a real attempt consume ZERO daily
    budget, and a run could then fire an unbounded number of applications
    at employers after the limit was supposed to be reached - the exact
    opposite of what the limit is for.
    """
    from indeed_scraper.apply.ledger import ApplicationLedger

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=1)

    assert ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitting", "")
    ledger.mark("fp-1", "unconfirmed", "submit_unconfirmed")

    assert ledger.submitted_today() == 1, (
        "an unconfirmed attempt must consume a slot of the daily budget"
    )
    assert budget.can_apply(ledger) is False, (
        "the budget must be exhausted by an unconfirmed attempt"
    )
    # And the posting must not be retryable: it may already have reached
    # the employer.
    assert ledger.status_of("fp-1") == "unconfirmed"
    assert ledger.reserve("fp-1", "jk", "u") is False


def test_a_positive_daily_cap_still_allows_up_to_the_limit(tmp_path: Path) -> None:
    """The ordinary cap keeps working after the non-positive cap is closed."""
    from indeed_scraper.apply.ledger import ApplicationLedger

    ledger = ApplicationLedger(tmp_path / "ledger.jsonl")
    budget = RiskBudget(max_per_day=2)

    assert budget.can_apply(ledger) is True
    ledger.reserve("fp-1", "jk", "u")
    ledger.mark("fp-1", "submitted", "")
    assert budget.can_apply(ledger) is True
    ledger.reserve("fp-2", "jk", "u")
    ledger.mark("fp-2", "submitted", "")
    assert budget.can_apply(ledger) is False


# ---------------------------------------------------------------------------
# A1 - the submit contract
# ---------------------------------------------------------------------------

class _SubmitLocator:
    """Playwright Locator stand-in for the submit control."""

    def __init__(self, page: _SubmitPage, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> _SubmitLocator:
        return self

    def count(self) -> int:
        return 1 if self._selector in self._page.visible else 0

    def is_visible(self, timeout: int = 0) -> bool:
        return self._selector in self._page.visible

    def click(self, timeout: int = 0) -> None:
        self._page.clicks.append(self._selector)
        self._page.navigated = True


class _SubmitPage:
    """Page stand-in that models what a real submit click does.

    * the URL and the title change (the click navigates),
    * the body may carry a confirmation,
    * the READ after the click may raise, exactly as it does in a real
      browser when the navigation destroys the execution context.
    """

    def __init__(
        self,
        url: str = "https://ca.indeed.com/apply/in/jk1",
        title: str = "Apply",
        body: str = "",
        raise_on_read: bool = False,
    ) -> None:
        self.url = url
        self.title_text = title
        self.body_text = body
        self.raise_on_read = raise_on_read
        self.navigated = False
        self.clicks: list[str] = []
        # A real page matches BOTH 'button:has-text("Submit application")' and
        # 'button:has-text("Submit")' - the same button.
        self.visible = set(SUBMIT_SELECTORS)

    def locator(self, selector: str) -> _SubmitLocator:
        return _SubmitLocator(self, selector)

    def wait_for_timeout(self, ms: int) -> None:
        return None

    def title(self) -> str:
        if self.raise_on_read and self.navigated:
            raise RuntimeError("Execution context was destroyed, most likely because of navigation")
        return self.title_text

    def content(self) -> str:
        if self.raise_on_read and self.navigated:
            raise RuntimeError("Execution context was destroyed, most likely because of navigation")
        return f"<html><body>{self.body_text}</body></html>"


def test_an_unconfirmed_submit_is_not_reported_as_a_success() -> None:
    """A click with NO success signal must NOT be reported as submitted.

    The old code returned True from the fall-through ("the click succeeded even
    without an explicit signal"), so a submission that never happened was
    recorded as one.
    """
    page = _SubmitPage()
    result = submit_application(page)

    assert result.confirmed is False
    assert result.clicked is True


def test_a_confirmed_submit_reports_success() -> None:
    """A real success signal must still be reported as a success."""
    page = _SubmitPage(title="Application Submitted")
    result = submit_application(page)

    assert result.confirmed is True
    assert result.clicked is True


def test_a_confirmation_in_the_markup_is_a_success() -> None:
    """The confirmation is often only in the page body."""
    page = _SubmitPage(body="<h1>Your application has been submitted</h1>")
    result = submit_application(page)

    assert result.confirmed is True


def test_the_submit_button_is_clicked_at_most_once() -> None:
    """A read failure after the click must not trigger a second click.

    The old code caught the post-click exception and continued to the NEXT
    selector, which matched the SAME button and clicked it again - a double
    application.
    """
    page = _SubmitPage(raise_on_read=True)
    result = submit_application(page)

    assert len(page.clicks) == 1, (
        f"the submit button was clicked {len(page.clicks)} times: {page.clicks!r}"
    )
    assert result.clicked is True
    assert result.confirmed is False


def test_no_submit_control_means_nothing_was_clicked() -> None:
    """With no submit control, nothing is clicked and nothing is confirmed."""
    page = _SubmitPage()
    page.visible = set()
    result = submit_application(page)

    assert result.clicked is False
    assert result.confirmed is False
    assert page.clicks == []
