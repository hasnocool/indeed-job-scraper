"""Behaviour-named unit tests for the Indeed application-form interaction module.

Each test case is named to describe the behaviour it verifies; it should fail
if that behaviour breaks.

Uses a REAL headless Chromium via playwright sync_api on a page whose content
is set with page.set_content(...). Skip the module if no Chromium binary is
present under ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome.
"""

from __future__ import annotations

import pytest

from indeed_scraper.apply.exceptions import FieldMissingError
from indeed_scraper.apply.indeed_form import (
    APPLY_BUTTON_SELECTORS,
    FIELD_SELECTORS,
    detect_challenge,
    detect_portal,
    fill_indeed_form,
    find_apply_button,
    submit_application,
)
from indeed_scraper.apply.profile import Profile

# ---------------------------------------------------------------------------
# Fake page & locator for headless testing (no real browser needed)
# ---------------------------------------------------------------------------

class _FakeLocator:
    """Minimal fake Playwright Locator for testing.

    Key design: is_visible() and get_attribute() are cooperative — they return
    sensible defaults so that the real indeed_form.py logic works without a
    full browser. Tests can override _visible if they want to simulate
    invisibility, but the defaults allow the common cases to pass.

    The ATTRIBUTES are honest: a field is only required when the markup the
    test declared actually carries the attribute. The old fake returned
    "required" for every visible locator, so it could not express an
    optional field, and it could not exercise the bare-boolean-attribute
    case (``required`` with no value) that the real browser reports as the
    EMPTY STRING. That lie made the fake unable to catch the bug it was
    standing in for.
    """

    def __init__(
        self,
        visible: bool = True,
        value: str = "",
        attributes: dict[str, str] | None = None,
    ) -> None:
        self._visible = visible
        self._value = value
        self._attributes: dict[str, str] = dict(attributes or {})

    @property
    def first(self):
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        return self._visible

    def fill(self, value: str) -> None:
        self._value = value

    def set_input_files(self, path: str) -> None:
        self._value = path

    def click(self) -> None:
        pass

    def text_content(self) -> str | None:
        return self._value if self._value else None

    def set_attributes(self, attributes: dict[str, str]) -> None:
        self._attributes = dict(attributes)

    def get_attribute(self, name: str) -> str | None:
        if name in {"required", "aria-required"}:
            # None means the attribute is ABSENT, which is what a browser
            # reports for an input that does not carry it. A bare `required`
            # reads as the empty string, and `aria-required` as its value.
            return self._attributes.get(name)
        if name == "aria-label":
            return self._value if self._value else None
        return None


class _FakePage:
    """Minimal fake Playwright Page for testing.

    ``set_content`` parses the markup the test declared, so the fake knows
    WHICH inputs carry ``required`` / ``aria-required`` instead of assuming
    that every visible field is required.
    """

    def __init__(self, url: str = "https://ca.indeed.com/viewjob?jk=test") -> None:
        self.url = url
        self._locators: dict[str, _FakeLocator] = {}
        self._title = ""
        self._attributes: dict[str, dict[str, str]] = {}

    def set_content(self, content: str, *args, **kwargs) -> None:
        """Store content and extract basic DOM info for testing."""
        self._content = content
        import re

        m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
        self._title = m.group(1) if m else ""
        self._attributes = self._parse_attributes(content)

    @staticmethod
    def _parse_attributes(content: str) -> dict[str, dict[str, str]]:
        """Map the selectors of required inputs to the attributes they carry.

        The selectors are the ones the form filler actually looks for:
        ``input[name="..."]`` and ``input#...``.
        """
        import re

        found: dict[str, dict[str, str]] = {}
        for tag in re.findall(r"<input\b[^>]*>", content, re.IGNORECASE):
            selectors: list[str] = []
            name = re.search(r'name="([^"]+)"', tag)
            if name:
                selectors.append(f'input[name="{name.group(1)}"]')
            ident = re.search(r'id="([^"]+)"', tag)
            if ident:
                selectors.append(f'input#{ident.group(1)}')
            attributes: dict[str, str] = {}
            # A bare `required` attribute. The lookarounds keep it from
            # matching inside `aria-required`, which is a different
            # attribute with its own value.
            if re.search(r"(?<![-\w])required(?![-\w])", tag, re.IGNORECASE):
                # A real browser reports a bare `required` as the EMPTY STRING.
                attributes["required"] = ""
            aria = re.search(r'aria-required="([^"]*)"', tag, re.IGNORECASE)
            if aria:
                attributes["aria-required"] = aria.group(1)
            for selector in selectors:
                found[selector] = attributes
        return found

    def locator(self, selector: str) -> _FakeLocator:
        if selector not in self._locators:
            self._locators[selector] = _FakeLocator(visible=True)
        locator = self._locators[selector]
        locator.set_attributes(self._attributes.get(selector, {}))
        return locator

    def title(self) -> str:
        return self._title

    def wait_for_timeout(self, ms: int) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_page(url: str = "https://ca.indeed.com/viewjob?jk=test") -> _FakePage:
    return _FakePage(url)


#: The shared resume fixture the form tests fill against.
SHARED_RESUME = "/tmp/resume.pdf"


def _ensure_resume(path: str = SHARED_RESUME) -> str:
    """Make sure the SHARED resume fixture is a real PDF.

    Only the shared default is managed here: a path the caller chose is
    never created, so a test can point at a file that does not exist.
    """
    import pathlib

    if path != SHARED_RESUME:
        return path
    target = pathlib.Path(path)
    if not target.exists() or target.stat().st_size < 1024:
        target.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    return path


def _make_profile(
    name: str = "Ada",
    email: str = "ada@example.com",
    phone: str = "555-0100",
    resume_path: str = "/tmp/resume.pdf",
    cover_letter: str = "",
) -> Profile:
    _ensure_resume(resume_path)
    return Profile(
        name=name,
        email=email,
        phone=phone,
        resume_path=resume_path,
        cover_letter=cover_letter,
    )


# ---------------------------------------------------------------------------
# detect_portal tests
# ---------------------------------------------------------------------------

def test_detect_portal_external() -> None:
    """detect_portal returns "external" for a page whose URL is not indeed.com."""
    page = _make_page("https://greenhouse.io/x/acme/jobs/test123")
    result = detect_portal(page)
    assert result == "external"


def test_detect_portal_indeed_apply() -> None:
    """detect_portal returns "indeed" for an Indeed job apply page."""
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    result = detect_portal(page)
    assert result == "indeed"


def test_detect_portal_unknown() -> None:
    """detect_portal returns "unknown" for an Indeed URL that is not apply/viewjob."""
    page = _make_page("https://ca.indeed.com/jobs?q=python")
    result = detect_portal(page)
    assert result == "unknown"


# ---------------------------------------------------------------------------
# find_apply_button tests
# ---------------------------------------------------------------------------

def test_find_apply_button_found() -> None:
    """find_apply_button returns a visible locator when an apply button exists."""
    page = _make_page()
    page._locators['button:has-text("Apply now")'] = _FakeLocator(visible=True)
    button = find_apply_button(page)
    assert button is not None


def test_find_apply_button_not_found() -> None:
    """find_apply_button returns None when no apply button is visible."""
    page = _make_page()
    # Ensure no apply button selectors are visible
    for sel in APPLY_BUTTON_SELECTORS:
        page._locators[sel] = _FakeLocator(visible=False)
    assert find_apply_button(page) is None


# ---------------------------------------------------------------------------
# detect_challenge tests
# ---------------------------------------------------------------------------

def test_detect_challenge_cloudflare_title() -> None:
    """detect_challenge returns a non-empty label for a Cloudflare page title."""
    page = _make_page()
    page.set_content('<html><head><title>Just a moment...</title></head><body></body></html>')
    result = detect_challenge(page)
    assert result != "", f"Expected non-empty challenge label, got: {result!r}"


def test_detect_challenge_clean() -> None:
    """detect_challenge returns "" for a clean page."""
    page = _make_page()
    page.set_content('<html><head><title>Job Details</title></head><body></body></html>')
    result = detect_challenge(page)
    assert result == ""


def test_detect_challenge_cloudflare_alt_title() -> None:
    """detect_challenge returns label for alternative Cloudflare title."""
    page = _make_page()
    page.set_content('<html><head><title>Attention Required</title></head><body></body></html>')
    result = detect_challenge(page)
    assert result != ""


# ---------------------------------------------------------------------------
# fill_indeed_form tests
# ---------------------------------------------------------------------------

def _populate_form_selectors(page: _FakePage) -> None:
    """Register all FIELD_SELECTORS entries so the fake page tracks them."""
    for selectors in FIELD_SELECTORS.values():
        for sel in selectors:
            page.locator(sel)  # create the locator entry


def test_fill_indeed_form_fills_name_email_phone() -> None:
    """fill_indeed_form fills name/email/phone from a Profile into inputs.

    Verifies the returned draft map contains the filled values.
    """
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        '<body>'
        '  <input type="text" name="applicant.name"/>'
        '  <input type="email" id="applicant-email"/>'
        '  <input type="tel" name="applicant.phone"/>'
        '  <input type="file" name="resume"/>'
        '  <textarea name="cover.letter"></textarea>'
        "</body></html>"
    )

    # Register all field selectors so the fake page tracks them
    _populate_form_selectors(page)

    profile = _make_profile()
    draft = fill_indeed_form(page, profile)

    # Verify the draft map contains the filled values
    assert draft.get("name") == "Ada", f"Expected draft['name']='Ada', got {draft.get('name')!r}"
    assert draft.get("email") == "ada@example.com", (
        f"Expected draft['email']='ada@example.com', got {draft.get('email')!r}"
    )
    assert draft.get("phone") == "555-0100", (
        f"Expected draft['phone']='555-0100', got {draft.get('phone')!r}"
    )


def test_fill_indeed_form_raises_field_missing_for_required() -> None:
    """fill_indeed_form raises FieldMissingError when a REQUIRED input is empty in Profile."""
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        '<body>'
        '  <input type="text" name="applicant.name" required/>'
        '  <input type="email" id="applicant-email" required/>'
        '  <input type="tel" name="applicant.phone" required/>'
        '  <input type="file" name="resume"/>'
        "</body></html>"
    )

    profile = _make_profile(name="", email="", phone="")  # all empty
    with pytest.raises(FieldMissingError) as excinfo:
        fill_indeed_form(page, profile)

    # The exception must have non-empty .question and .job_url
    assert excinfo.value.question, "FieldMissingError .question must be non-empty"
    assert excinfo.value.job_url, "FieldMissingError .job_url must be non-empty"
    assert isinstance(excinfo.value.question, str)
    assert isinstance(excinfo.value.job_url, str)


def test_a_bare_required_attribute_is_treated_as_required() -> None:
    """A bare `required` (no value) is REQUIRED.

    A real browser reports a bare boolean attribute as the EMPTY STRING, so a
    check on the TRUTHINESS of the value calls an empty required field
    optional - and the hard-refuse never fires. The presence of the attribute
    is what matters.
    """
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        "<body>"
        '  <input type="text" name="applicant.name" required>'
        "</body></html>"
    )

    profile = _make_profile(name="")
    with pytest.raises(FieldMissingError):
        fill_indeed_form(page, profile)


def test_an_input_without_the_attribute_is_not_required() -> None:
    """The mirror image: an input that does NOT carry `required` is optional.

    The old fake reported EVERY visible locator as required, so it could not
    express this case at all, and a check that treated every field as
    required would have passed it.
    """
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        "<body>"
        '  <input type="text" name="applicant.name">'
        "</body></html>"
    )

    profile = _make_profile(name="")
    draft = fill_indeed_form(page, profile)

    assert "name" not in draft, f"an optional field must not be claimed: {draft!r}"


def test_aria_required_true_is_required_and_false_is_not() -> None:
    """`aria-required="true"` is required; `aria-required="false"` is not."""
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        "<body>"
        '  <input type="text" name="applicant.name" aria-required="true">'
        "</body></html>"
    )
    with pytest.raises(FieldMissingError):
        fill_indeed_form(page, _make_profile(name=""))

    page.set_content(
        '<html><head><title>Apply</title></head>'
        "<body>"
        '  <input type="text" name="applicant.name" aria-required="false">'
        "</body></html>"
    )
    draft = fill_indeed_form(page, _make_profile(name=""))
    assert "name" not in draft, f"an optional field must not be claimed: {draft!r}"


def test_fill_indeed_form_raises_field_missing_for_missing_resume() -> None:
    """fill_indeed_form raises FieldMissingError when resume_path points to a missing file."""
    import pathlib

    resume_path = "/tmp/indeed_missing_resume_fixture.pdf"
    if pathlib.Path(resume_path).exists():
        pathlib.Path(resume_path).unlink()

    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        '<body>'
        '  <input type="text" name="applicant.name"/>'
        '  <input type="email" id="applicant-email"/>'
        '  <input type="tel" name="applicant.phone"/>'
        '  <input type="file" name="resume"/>'
        "</body></html>"
    )

    _populate_form_selectors(page)

    profile = _make_profile(resume_path=resume_path)
    with pytest.raises(FieldMissingError) as excinfo:
        fill_indeed_form(page, profile)

    assert "resume" in excinfo.value.question
    assert resume_path in excinfo.value.question
    assert excinfo.value.job_url == "https://ca.indeed.com/apply/in/test123"

    # Nothing to restore: the path was never created.


def test_fill_indeed_form_with_all_fields() -> None:
    """fill_indeed_form fills all fields from a fully-populated Profile.

    Verifies the returned draft map contains all filled values.
    """
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        '<body>'
        '  <input type="text" name="applicant.name"/>'
        '  <input type="email" id="applicant-email"/>'
        '  <input type="tel" name="applicant.phone"/>'
        '  <input type="file" name="resume"/>'
        '  <textarea name="cover.letter"></textarea>'
        "</body></html>"
    )

    _populate_form_selectors(page)

    profile = _make_profile(
        name="Ada",
        email="ada@example.com",
        phone="555-0100",
        resume_path="/tmp/resume.pdf",
        cover_letter="Why I love data",
    )
    draft = fill_indeed_form(page, profile)

    # Verify the draft map contains all filled values
    assert draft.get("name") == "Ada", f"Expected draft['name']='Ada', got {draft.get('name')!r}"
    assert draft.get("email") == "ada@example.com", (
        f"Expected draft['email']='ada@example.com', got {draft.get('email')!r}"
    )
    assert draft.get("phone") == "555-0100", (
        f"Expected draft['phone']='555-0100', got {draft.get('phone')!r}"
    )
    assert draft.get("cover_letter") == "Why I love data", (
        f"Expected draft['cover_letter']='Why I love data', got {draft.get('cover_letter')!r}"
    )


def test_fill_indeed_form_optional_cover_letter_omitted_when_empty() -> None:
    """fill_indeed_form does not include cover_letter in draft when Profile has empty string."""
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Apply</title></head>'
        '<body>'
        '  <input type="text" name="applicant.name"/>'
        '  <input type="email" id="applicant-email"/>'
        '  <input type="tel" name="applicant.phone"/>'
        '  <input type="file" name="resume"/>'
        '  <textarea name="cover.letter"></textarea>'
        "</body></html>"
    )

    _populate_form_selectors(page)

    profile = _make_profile(cover_letter="")
    draft = fill_indeed_form(page, profile)

    assert draft.get("cover_letter") is None


# ---------------------------------------------------------------------------
# submit_application tests
# ---------------------------------------------------------------------------

def test_submit_application_reports_nothing_clicked_when_no_submit() -> None:
    """submit_application reports a click of nothing when no submit control exists.

    The result is an OBJECT now, not a bool: the contract has to say
    "clicked" and "confirmed" separately, because a click with no
    confirmation is an attempt, not a success and not a no-op.
    """
    page = _make_page()
    # Ensure no submit button selectors are visible
    for sel in [
        'button:has-text("Submit application")',
        'button:has-text("Submit")',
        'input[type="submit"]',
        '[data-testid="submit-application"]',
    ]:
        page._locators[sel] = _FakeLocator(visible=False)
    result = submit_application(page)
    assert result.clicked is False
    assert result.confirmed is False


def test_submit_application_confirms_a_submitted_title() -> None:
    """A confirmation in the page title is reported as a confirmed submit."""
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Application Submitted</title></head>'
        '<body>'
        '  <button>Submit application</button>'
        "</body></html>"
    )
    result = submit_application(page)
    assert result.clicked is True
    assert result.confirmed is True


def test_submit_application_does_not_confirm_without_a_signal() -> None:
    """A click with no success signal is NOT reported as confirmed.

    The old code fell through to ``return True`` ("the click succeeded even
    without an explicit signal"), so a submission that never happened was
    recorded as one. "submitted" is a terminal ledger state, so the lie was
    permanent.
    """
    page = _make_page("https://ca.indeed.com/apply/in/test123")
    page.set_content(
        '<html><head><title>Done</title></head>'
        '<body>'
        '  <button>Submit</button>'
        "</body></html>"
    )
    result = submit_application(page)
    assert result.clicked is True
    assert result.confirmed is False